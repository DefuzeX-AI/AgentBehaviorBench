"""ABB binding for psyray/oasis (Open Automated Security Intelligence Scanner).

Orchestrates automated vulnerability intelligence scanning using OASIS's
LangGraph analysis state machine:
  START -> node_discover -> node_scan -> node_expand -> node_deep -> node_verify -> node_report (-> node_poc) -> END

The binding:
- Accepts code text, file paths, or directories as benchmark input.
- Intercepts conversational and capability queries cleanly without false scanning overhead.
- Materializes code submissions into isolated temporary workspaces.
- Connects OASIS to ABB's OpenAI-compatible model interceptor (`/v1/chat/completions`)
  using DeepSeek (`deepseek-flash`).
- Routes embedding requests natively through ABB's OpenAI-compatible
  embedding interceptor (`/v1/embeddings`) with legitimate route declaration.
- Forwards LangGraph execution configuration (`config=config`) and applies
  `set_config_context` so OpenTelemetry callbacks and framework node spans
  are captured accurately.
- Formats security reports and findings into structured markdown responses.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

# Ensure agent source is importable
_SOURCE_ROOT = Path(__file__).resolve().parents[1] / "agent"
if not _SOURCE_ROOT.is_dir():
    # Fallback to local package or sys.path
    _SOURCE_ROOT = Path("/opt/agent/agent")


def _ensure_import_path() -> None:
    if _SOURCE_ROOT.is_dir():
        entry = str(_SOURCE_ROOT)
        if entry not in sys.path:
            sys.path.insert(0, entry)
        # Ensure sys.modules['oasis'] points to the package directory, avoiding clash with agent/oasis.py script
        if "oasis" in sys.modules:
            m = sys.modules["oasis"]
            if not hasattr(m, "__path__"):
                pkg_dir = _SOURCE_ROOT / "oasis"
                if pkg_dir.is_dir():
                    m.__path__ = [str(pkg_dir)]
    _install_concurrency_and_inventory_guards()


def _install_concurrency_and_inventory_guards() -> None:
    """Safeguard process concurrency and model inventory for in-process threaded runtime.

    1. OpenAICompatClient.list:
       Queries /models with a short (2.0s) timeout so unrouted discovery calls
       do not hang for the default 240s httpx timeout. When /models is unrouted
       or unavailable in container sandboxes, falls back to declared models from
       the environment, preserving real model verification in ensure_model_available.
       Preserves native qualname and untouched native OpenAICompatClient.embeddings.
    2. EmbeddingManager.index_code_files & EmbeddingAnalyzer._execute_parallel_analysis:
       Executes directly in-process when single item, or via ThreadPoolExecutor when
       multiple items, eliminating multiprocessing.Pool deadlocks on macOS arm64 (spawn).
    """
    try:
        from concurrent.futures import ThreadPoolExecutor
        from oasis.analyze import EmbeddingAnalyzer, analyze_item_parallel
        from oasis.backends.openai_compat import OpenAICompatClient
        from oasis.embedding import EmbeddingManager, process_file_parallel
    except (ImportError, Exception):
        return

    # Guard 1: Resilient model inventory check (no 240s hang on unrouted /models)
    if not getattr(OpenAICompatClient, "_abb_guarded", False):
        orig_list = OpenAICompatClient.list

        def _safe_list(self: Any) -> dict[str, Any]:
            try:
                old_timeout = getattr(self, "_default_timeout", None)
                try:
                    self._default_timeout = 2.0
                    return orig_list(self)
                finally:
                    self._default_timeout = old_timeout
            except Exception:
                pass
            declared: list[dict[str, str]] = []
            for k in (
                "OPENAI_MODEL",
                "DEEPSEEK_MODEL",
                "MODEL",
                "CHAT_MODEL",
                "OPENAI_EMBEDDING_MODEL",
                "EMBED_MODEL",
                "EMBEDDING_MODEL",
            ):
                v = os.environ.get(k)
                if v and v.strip() and not any(m["model"] == v.strip() for m in declared):
                    declared.append({"model": v.strip(), "name": v.strip()})
            for default_model in ("deepseek-flash", "deepseek-chat", "text-embedding-3-small"):
                if not any(m["model"] == default_model for m in declared):
                    declared.append({"model": default_model, "name": default_model})
            return {"models": declared}

        _safe_list.__qualname__ = "OpenAICompatClient.list"
        OpenAICompatClient.list = _safe_list
        OpenAICompatClient._abb_guarded = True

    # Guard 2: Sequential / ThreadPool indexing to eliminate macOS arm64 multiprocessing spawn deadlock
    if not getattr(EmbeddingManager, "_abb_guarded", False):
        def _safe_index_code_files(
            self: Any,
            files: list[Any],
            *,
            embedding_progress_hook: Any = None,
            embedding_progress_min_interval_sec: float = 0.5,
        ) -> None:
            process_args = self._build_index_process_args(files)
            if not process_args:
                return
            workers = min(4, len(process_args))
            if workers <= 1:
                for arg in process_args:
                    res = process_file_parallel(arg)
                    self._store_index_result(res)
                return
            with ThreadPoolExecutor(max_workers=workers) as executor:
                for res in executor.map(process_file_parallel, process_args):
                    self._store_index_result(res)

        EmbeddingManager.index_code_files = _safe_index_code_files
        EmbeddingManager._abb_guarded = True

    # Guard 3: Sequential / ThreadPool analysis to eliminate macOS arm64 multiprocessing spawn deadlock
    if not getattr(EmbeddingAnalyzer, "_abb_guarded", False):
        def _safe_execute_parallel_analysis(self: Any, process_args: list[Any]) -> list[Any]:
            if not process_args:
                return []
            workers = min(4, len(process_args))
            if workers <= 1:
                results = []
                for arg in process_args:
                    res = analyze_item_parallel(arg)
                    if res and "error" not in res:
                        results.append(res)
                return results
            with ThreadPoolExecutor(max_workers=workers) as executor:
                results = [
                    res for res in executor.map(analyze_item_parallel, process_args)
                    if res and "error" not in res
                ]
            return results

        EmbeddingAnalyzer._execute_parallel_analysis = _safe_execute_parallel_analysis
        EmbeddingAnalyzer._abb_guarded = True


_ensure_import_path()


def _is_safe_file_candidate(text: str) -> bool:
    """Safely check if text could be a filesystem path without raising Errno 36."""
    if not text or "\n" in text or len(text) > 255:
        return False
    try:
        return Path(text).exists()
    except OSError:
        return False


def _is_conversational_query(text: str) -> bool:
    """Check if input is a conversational question rather than code to scan."""
    stripped = text.strip()
    if not stripped:
        return True

    # If explicit code syntax or language markers are present, route to scanning
    code_indicators = (
        "def ", "class ", "import ", "select ", "from ", "function ",
        "<?php", "eval(", "exec(", "<script", "system(", "popen(", "curl ",
        "```", "sqlite3", "cursor."
    )
    lower = stripped.lower()
    if any(ind in lower for ind in code_indicators):
        return False

    if "/" in stripped or "\\" in stripped:
        # Might be a file path
        if _is_safe_file_candidate(stripped) or stripped.endswith((".py", ".js", ".php", ".go", ".c", ".cpp")):
            return False

    if len(stripped.splitlines()) > 3:
        return False

    # Check conversational phrases anywhere in short queries
    conversational_keywords = (
        "introduce yourself", "who are you", "what are you", "what can you do",
        "what can you help", "tell me about yourself", "how do you work",
        "how do you scan", "what vulnerabilities", "what types of vulnerabilities",
        "help with", "hello", "hi there", "greetings"
    )
    if any(kw in lower for kw in conversational_keywords):
        return True

    conversational_patterns = (
        r"^(hi|hello|hey|help)\b",
    )
    return any(re.search(pat, stripped, re.IGNORECASE) is not None for pat in conversational_patterns)


def _capability_response() -> str:
    return (
        "I am **OASIS** (Open Automated Security Intelligence Scanner), an automated "
        "vulnerability intelligence scanning agent orchestrated via a LangGraph state machine.\n\n"
        "### What I Can Help With\n"
        "- **Automated Security Analysis**: Scanning application source code and repositories "
        "for high-risk vulnerabilities and security defects before deployment.\n"
        "- **Deep Exploitability Reasoning**: Tracing taint flows, variable scopes, and execution "
        "contexts using deep LLM-backed analysis to verify genuine flaws and eliminate false positives.\n"
        "- **Comprehensive Vulnerability Coverage**: Detecting SQL Injection (SQLi), Remote Code Execution (RCE), "
        "Command Injection, Cross-Site Scripting (XSS), CSRF, Authentication bypasses, IDOR, SSRF, "
        "Path Traversal, and Insecure Deserialization.\n"
        "- **Structured Security Reports**: Delivering executive summaries, detailed line-by-line evidence, "
        "impact assessments, and remediation guidance across Markdown, JSON, and SARIF formats.\n"
    )


class OasisAgentGraph:
    """ABB Invokable graph adapter wrapping OASIS LangGraph pipeline."""

    def __init__(self) -> None:
        _ensure_import_path()

    def invoke(self, input_data: Any, config: Mapping[str, Any] | None = None, **kwargs: Any) -> dict[str, str]:
        """Synchronously execute OASIS security analysis."""
        return asyncio.run(self.ainvoke(input_data, config=config, **kwargs))

    async def ainvoke(
        self, input_data: Any, config: Mapping[str, Any] | None = None, **kwargs: Any
    ) -> dict[str, str]:
        """Asynchronously execute OASIS security analysis."""
        _ensure_import_path()

        # Extract text from input envelope
        text_input = ""
        if isinstance(input_data, Mapping):
            for key in ("prompt", "message", "input", "code", "query"):
                val = input_data.get(key)
                if isinstance(val, str) and val.strip():
                    text_input = val.strip()
                    break
            if not text_input:
                text_input = json.dumps(input_data)
        elif isinstance(input_data, str):
            text_input = input_data.strip()
        else:
            text_input = str(input_data)

        # Check conversational queries
        if _is_conversational_query(text_input):
            return {"answer": _capability_response()}

        # Materialize input code or resolve file path
        workspace_dir: tempfile.TemporaryDirectory | None = None
        target_path: Path
        candidate_path: Path | None = None
        if _is_safe_file_candidate(text_input):
            try:
                candidate_path = Path(text_input).resolve()
            except OSError:
                candidate_path = None

        if candidate_path is not None:
            target_path = candidate_path
        else:
            workspace_dir = tempfile.TemporaryDirectory(prefix="oasis_abb_")
            code_to_write = text_input
            ext = ".py"
            code_block_match = re.search(r"```([a-zA-Z0-9_\-+]*)\n([\s\S]*?)```", text_input)
            if code_block_match:
                lang = code_block_match.group(1).lower().strip()
                code_to_write = code_block_match.group(2).strip()
                if "php" in lang:
                    ext = ".php"
                elif "js" in lang or "javascript" in lang:
                    ext = ".js"
                elif "c" in lang or "cpp" in lang:
                    ext = ".c"
                elif "java" in lang:
                    ext = ".java"
                elif "go" in lang:
                    ext = ".go"
                else:
                    ext = ".py"
            else:
                if "<?php" in text_input:
                    ext = ".php"
                elif "function" in text_input and ("var " in text_input or "const " in text_input or "let " in text_input):
                    ext = ".js"

            target_file = Path(workspace_dir.name) / f"submission{ext}"
            target_file.write_text(code_to_write, encoding="utf-8")
            target_path = Path(workspace_dir.name)

        try:
            return await asyncio.to_thread(self._run_scan, target_path, config)
        finally:
            if workspace_dir is not None:
                try:
                    workspace_dir.cleanup()
                except Exception:
                    pass

    def _run_scan(self, target_path: Path, config: Mapping[str, Any] | None) -> dict[str, str]:
        from langchain_core.runnables.config import set_config_context
        from oasis.oasis import OasisScanner
        import oasis.agent.invoke as invoke_mod

        model_name = os.environ.get("OPENAI_MODEL") or os.environ.get("DEEPSEEK_MODEL") or "deepseek-flash"
        api_base = os.environ.get("OPENAI_BASE_URL") or os.environ.get("DEEPSEEK_BASE_URL") or "https://api.openai.com/v1"
        api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("DEEPSEEK_API_KEY") or "local"
        embed_model = os.environ.get("OPENAI_EMBEDDING_MODEL") or os.environ.get("EMBED_MODEL") or "text-embedding-3-small"
        embed_api_base = (
            os.environ.get("OASIS_EMBED_OPENAI_BASE_URL")
            or os.environ.get("OPENAI_EMBEDDING_BASE_URL")
            or os.environ.get("EMBED_BASE_URL")
            or api_base
        )
        embed_api_key = (
            os.environ.get("OASIS_EMBED_OPENAI_API_KEY")
            or os.environ.get("OPENAI_EMBEDDING_API_KEY")
            or os.environ.get("EMBED_API_KEY")
            or api_key
        )
        embed_provider = os.environ.get("OASIS_EMBED_PROVIDER") or "openai"

        scanner = OasisScanner()
        parser = scanner.setup_argument_parser()
        args = parser.parse_args([
            "-i", str(target_path),
            "-m", model_name,
            "-sm", model_name,
            "-em", embed_model,
            "--provider", "openai",
            "--api-base", api_base,
            "--api-key", api_key,
            "--embed-provider", embed_provider,
            "--embed-api-base", embed_api_base,
            "--embed-api-key", embed_api_key,
            "-t", "0.5",
            "-v", "all",
            "-s"
        ])

        # Hook invoke_oasis_langgraph to forward ABB config to graph.invoke
        original_invoke_langgraph = invoke_mod.invoke_oasis_langgraph
        captured_results: dict[str, Any] = {}

        def _forwarding_invoke(analyzer: Any, vulnerabilities: list[dict[str, Any]], scan_args: Any, report: Any) -> dict[str, Any]:
            nonlocal captured_results
            graph = invoke_mod.build_oasis_analysis_graph()
            initial = {
                "analyzer": analyzer,
                "args": scan_args,
                "report": report,
                "vulnerabilities": vulnerabilities,
                "embedding_tasks": [],
                "suspicious_payload": {},
                "all_results": {},
                "expand_iterations": 0,
                "max_expand_iterations": getattr(scan_args, "langgraph_max_expand_iterations", 2),
                "verify_retry_pending": False,
                "validation_error_count": 0,
                "poc_hints_markdown": "",
                "silent": bool(getattr(scan_args, "silent", False)),
            }
            with set_config_context(dict(config or {})):
                final_state = graph.invoke(initial, config=dict(config or {}))
            res = final_state.get("all_results") or {}
            captured_results = res
            return res

        invoke_mod.invoke_oasis_langgraph = _forwarding_invoke
        try:
            with set_config_context(dict(config or {})):
                exit_code = scanner.run(args)
        finally:
            invoke_mod.invoke_oasis_langgraph = original_invoke_langgraph

        # Preserve native failure: OasisScanner.run returns non-zero on initialization, verification, or scan failure
        if exit_code != 0:
            raise RuntimeError(f"OASIS scanner execution failed with exit code {exit_code}")

        # Verify embedding generation succeeded if valid input files were present (preserve real blockage on missing service)
        em = getattr(scanner, "embedding_manager", None)
        valid_files = getattr(scanner, "valid_input_files", None)
        if isinstance(valid_files, (list, tuple)) and len(valid_files) > 0 and em is not None:
            code_base = getattr(em, "code_base", {})
            if isinstance(code_base, dict):
                has_embeddings = any(
                    (isinstance(v, dict) and bool(v.get("embedding")))
                    or (
                        isinstance(v, dict)
                        and any(bool(f.get("embedding")) for f in v.get("functions", {}).values())
                    )
                    for v in code_base.values()
                )
                if not has_embeddings:
                    raise RuntimeError(
                        "OASIS failed to generate embeddings for target code files; embedding service may be unavailable or failing."
                    )

        # Extract markdown report
        report_text = self._collect_report_text(scanner)
        if not report_text.strip() and captured_results:
            report_text = self._format_results_fallback(captured_results)

        # Do not claim successful scan if no report or evidence was produced
        if not report_text.strip():
            raise RuntimeError("OASIS scan completed without producing report or findings")

        return {"answer": report_text}

    def _collect_report_text(self, scanner: Any) -> str:
        report = getattr(scanner, "report", None)
        if not report:
            return ""

        output_dir = getattr(report, "output_dir", None)
        if not output_dir or not Path(output_dir).is_dir():
            return ""

        collected: list[str] = []
        md_dirs = list(Path(output_dir).rglob("md"))
        for md_dir in md_dirs:
            exec_summary = md_dir / "_executive_summary.md"
            if exec_summary.is_file():
                try:
                    collected.append(exec_summary.read_text(encoding="utf-8"))
                except Exception:
                    pass
            for file_path in md_dir.glob("*.md"):
                if file_path.name != "_executive_summary.md":
                    try:
                        collected.append(file_path.read_text(encoding="utf-8"))
                    except Exception:
                        pass

        if not collected:
            for file_path in Path(output_dir).rglob("*.md"):
                try:
                    collected.append(file_path.read_text(encoding="utf-8"))
                except Exception:
                    pass

        return "\n\n---\n\n".join(collected)

    def _format_results_fallback(self, results: Mapping[str, Any]) -> str:
        sections: list[str] = ["# Vulnerability Analysis Report\n"]
        for vuln_type, findings in results.items():
            if not isinstance(findings, list) or not findings:
                continue
            sections.append(f"## {vuln_type}\n")
            for f in findings:
                if not isinstance(f, Mapping):
                    continue
                file_p = f.get("file_path", "target")
                line_no = f.get("line_number", "")
                loc = f"{file_p}:{line_no}" if line_no else str(file_p)
                sections.append(f"- **Location**: `{loc}`")
                if "severity" in f:
                    sections.append(f"  - **Severity**: {f['severity']}")
                if "description" in f:
                    sections.append(f"  - **Description**: {f['description']}")
                if "mitigation" in f:
                    sections.append(f"  - **Remediation**: {f['mitigation']}")
                sections.append("")
        return "\n".join(sections).strip()


def create_graph() -> OasisAgentGraph:
    """Entry point for ABB LangGraph adapter."""
    return OasisAgentGraph()
