"""ABB binding for zamalali/langchain-code (LangCode).

Native contract (source under ``agent/`` is unchanged):

1. **Entrypoint.** LangCode is a Typer CLI (``langcode``). Its only mode that
   both keeps a multi-turn session and applies file changes is
   ``langcode chat --mode deep --auto``: ``cli/commands/chat.py`` builds the
   agent with ``build_deep_agent_with_optional_llm(provider, project_dir,
   llm, instruction_seed=AUTO_DEEP_INSTR, apply=auto)`` and, per user turn,
   appends ``{"role": "user", ...}`` and ``{"role": "system",
   "content": AUTOPILOT_PROMPT}`` to the running message list, then calls
   ``agent.invoke({"messages": msgs, "remaining_steps": 250},
   config={"recursion_limit": 45, "configurable": {"thread_id": ...}})``.
   ``45`` is ``prio_limits["balanced"]``, the default priority. When the last
   message is empty it appends a system nudge and invokes once more; a
   recursion error becomes "Agent hit recursion limit. Last response: ...".
   The binding repeats exactly that turn logic without the Rich UI.
   (``react`` chat never applies writes, and ``feature``/``fix`` invoke the
   ``create_agent`` graph with ``{"input": ...}`` instead of ``messages``.)

2. **Project directory.** The CLI operates on ``--project-dir``. Each binding
   instance owns one empty temporary project directory, kept for every input
   of the Case and removed on ``close()``. A Case input is the user's chat
   message; it can ask the agent to create, read, edit or run files there.

3. **Model.** ``--llm openai`` resolves to ``get_model("openai")``, a
   ``ChatOpenAI(model="gpt-4o-mini")`` at the default OpenAI endpoint, which is
   the route ``agent.toml`` declares. ABB's interception rewrites the request
   to the configured run model and supplies the credential.

4. **Tools.** glob, grep, list_dir, read_file, edit_by_diff, write_file,
   delete_file, run_cmd, script_exec, process_multimodal, the todo tools, the
   ``task`` sub-agent tool and the mermaid tools, rooted at the project
   directory with ``apply=True``. The packaged MCP config starts the GitHub MCP
   server through ``npx``; Node is not installed, so upstream's loader logs the
   failure and adds no MCP tools. Tavily is added only with ``TAVILY_API_KEY``,
   which this deployment does not provide. Mermaid PNG rendering calls
   mermaid.ink and has no egress.

5. **Configuration.** ABB's config (callbacks, tags) is merged under the
   native ``recursion_limit`` and ``thread_id`` defaults and passed to
   ``agent.invoke``.

Output: ``{"answer": <final assistant text>, "todos": [...], "files": [...]}``
where ``files`` lists the project directory after the turn (path and size).
Exceptions other than the recursion limit propagate.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "agent" / "src"
RECURSION_LIMIT = 45  # prio_limits["balanced"] in cli/commands/chat.py
EMPTY_NUDGE = "You must provide a response. Use your tools to complete the request and give a clear answer."
MAX_LISTED_FILES = 200


def _ensure_import_path() -> None:
    if str(SOURCE_ROOT) not in sys.path:
        sys.path.insert(0, str(SOURCE_ROOT))


def _message_text(value: Any) -> str:
    if isinstance(value, Mapping):
        if set(value) != {"message"}:
            raise ValueError("Supply text or exactly {'message': text}")
        value = value["message"]
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Case input must be a non-empty chat message")
    return value


def _list_files(root: Path) -> list[dict[str, Any]]:
    files = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and ".git" not in path.parts:
            files.append({"path": str(path.relative_to(root)), "bytes": path.stat().st_size})
            if len(files) >= MAX_LISTED_FILES:
                break
    return files


class LangCodeDeepChat:
    def __init__(self):
        self._workspace = Path(tempfile.mkdtemp(prefix="langcode-project-"))
        self._agent = None
        self._msgs: list[Any] = []
        self._thread_id: str | None = None

    def _build(self):
        _ensure_import_path()
        from langchain_code.cli_components.agents import build_deep_agent_with_optional_llm
        from langchain_code.config_core import get_model
        from langchain_code.workflows.auto import AUTO_DEEP_INSTR

        return build_deep_agent_with_optional_llm(
            provider="openai",
            project_dir=self._workspace,
            llm=get_model("openai"),
            instruction_seed=AUTO_DEEP_INSTR,
            apply=True,
        )

    def invoke(self, value, config=None):
        if self._workspace is None:
            raise RuntimeError("LangCode binding is closed")
        text = _message_text(value)
        if self._agent is None:
            self._agent = self._build()
        _ensure_import_path()
        from langchain_code.cli_components.runtime import extract_last_content, thread_id_for
        from langchain_code.static_values import AUTOPILOT_PROMPT

        if self._thread_id is None:
            case_thread = ((config or {}).get("configurable") or {}).get("thread_id")
            self._thread_id = f"{thread_id_for(self._workspace, 'chat')}#{case_thread or uuid.uuid4().hex}"
        run_config = dict(config or {})
        run_config.setdefault("recursion_limit", RECURSION_LIMIT)
        run_config["configurable"] = {**(run_config.get("configurable") or {}), "thread_id": self._thread_id}

        self._msgs.append({"role": "user", "content": text})
        self._msgs.append({"role": "system", "content": AUTOPILOT_PROMPT})

        output = ""
        last_content = ""
        res: dict = {}
        try:
            res = self._agent.invoke({"messages": self._msgs, "remaining_steps": 250}, config=run_config)
            if isinstance(res, dict) and "messages" in res:
                self._msgs = res["messages"]
                last_content = extract_last_content(self._msgs).strip()
        except Exception as e:
            if "recursion" not in str(e).lower():
                raise
            output = f"Agent hit recursion limit. Last response: {extract_last_content(self._msgs)}"
            res = {}
        if not output and not last_content:
            self._msgs.append({"role": "system", "content": EMPTY_NUDGE})
            res2 = self._agent.invoke({"messages": self._msgs, "remaining_steps": 250}, config=run_config)
            if isinstance(res2, dict) and "messages" in res2:
                self._msgs = res2["messages"]
                res = res2
            last_content = extract_last_content(self._msgs).strip()
        output = output or last_content or "No response generated."

        todos = res.get("todos") if isinstance(res, dict) else None
        return {
            "answer": output,
            "todos": todos if isinstance(todos, list) else [],
            "files": _list_files(self._workspace),
        }

    def close(self):
        workspace, self._workspace = self._workspace, None
        self._agent = None
        self._msgs = []
        if workspace is not None:
            shutil.rmtree(workspace, ignore_errors=True)


def create_graph():
    """Return a fresh binding; example input: 'Create hello.py that prints Hello and run it.'"""
    return LangCodeDeepChat()
