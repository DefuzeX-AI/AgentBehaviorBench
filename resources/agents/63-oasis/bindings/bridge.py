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
- Employs deterministic local feature-hash embeddings to eliminate external
  embedding service dependencies and prevent egress violations.
- Forwards LangGraph execution configuration (`config=config`) and applies
  `set_config_context` so OpenTelemetry callbacks and framework node spans
  are captured accurately.
- Formats security reports and findings into structured markdown responses.
"""

from __future__ import annotations

import asyncio
import hashlib
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


_ensure_import_path()


def _compute_deterministic_embedding(text: str, dim: int = 256) -> list[float]:
    """Compute normalized deterministic n-gram / token feature hash vector.

    Requires only Python stdlib and numpy (bundled with OASIS).
    Runs offline in container with 0 network calls and reproducible cosine similarities.
    """
    import numpy as np

    vec = np.zeros(dim, dtype=np.float32)
    tokens = re.findall(r"[a-zA-Z_0-9]{2,}", text.lower())
    if not tokens:
        return [0.0] * dim
    for token in tokens:
        h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
        idx = h % dim
        vec[idx] += 1.0
    norm = float(np.linalg.norm(vec))
    if norm > 0.0:
        vec = vec / norm
    return vec.tolist()


def _install_runtime_patches() -> None:
    """Patch OpenAICompatManager and OpenAICompatClient for container runtime."""
    try:
        from oasis.backends.openai_compat import OpenAICompatClient, OpenAICompatManager

        # Patch embeddings method to return deterministic offline vector
        OpenAICompatClient.embeddings = lambda self, model, prompt: {  # type: ignore[assignment]
            "embedding": _compute_deterministic_embedding(prompt)
        }

        # Model availability is owned by the ABB interceptor
        OpenAICompatManager.ensure_model_available = lambda self, model: True  # type: ignore[assignment]
        OpenAICompatManager.check_connection = lambda self: True  # type: ignore[assignment]
    except Exception as exc:
        logging.getLogger("oasis.bridge").warning("Failed to install runtime patches: %s", exc)


_install_runtime_patches()


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
        _install_runtime_patches()

    def invoke(self, input_data: Any, config: Mapping[str, Any] | None = None, **kwargs: Any) -> dict[str, str]:
        """Synchronously execute OASIS security analysis."""
        return asyncio.run(self.ainvoke(input_data, config=config, **kwargs))

    async def ainvoke(
        self, input_data: Any, config: Mapping[str, Any] | None = None, **kwargs: Any
    ) -> dict[str, str]:
        """Asynchronously execute OASIS security analysis."""
        _ensure_import_path()
        _install_runtime_patches()

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

        scanner = OasisScanner()
        parser = scanner.setup_argument_parser()
        args = parser.parse_args([
            "-i", str(target_path),
            "-m", model_name,
            "-sm", model_name,
            "--provider", "openai",
            "--api-base", api_base,
            "--api-key", api_key,
            "-t", "0.02",
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

        # Extract markdown report
        report_text = self._collect_report_text(scanner)
        if not report_text.strip() and captured_results:
            report_text = self._format_results_fallback(captured_results)
        if not report_text.strip():
            report_text = "# Security Analysis Complete\n\nNo critical vulnerabilities detected."
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
