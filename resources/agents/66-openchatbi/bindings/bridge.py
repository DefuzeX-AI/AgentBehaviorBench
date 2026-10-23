"""ABB binding for zhongyu09/openchatbi (OpenChatBI, a chat-based BI agent).

Native contract, verified in the imported snapshot under ``agent/``:

* ``openchatbi/__init__.py`` creates the ``ConfigLoader`` singleton ``config``
  and calls ``config.load()`` at import time. It reads ``CONFIG_FILE`` or
  ``openchatbi/config.yaml``; a missing file only logs and leaves the config
  unloaded, so this binding imports the package first and then loads its
  deployment YAML explicitly through the public ``config.load(path)``.
* ``run_cli.py`` is upstream's headless caller and the contract reproduced
  here: ``build_sync_graph`` is ``build_agent_graph_sync(catalog_store,
  checkpointer=MemorySaver(), memory_store=get_sync_memory_store(),
  llm_provider=None)``; ``build_run_config(user_id, session_id)`` supplies
  ``configurable.thread_id`` / ``user_id``, the ``ToolAuditCallback`` and
  tracing callbacks; one turn is ``graph.invoke({"messages": [{"role":
  "user", "content": question}]}, config)``; with streaming disabled the
  printed final answer is the content of the last message
  (``run_cli._handle_state``); when the graph stops at an ``AskHuman``
  interrupt the CLI shows the question and resumes the next turn with
  ``Command(resume=answer)``.
* The deployment is upstream's ``example/config.yaml``: the sqlite
  ``tracking_orders`` sales dataset with the file-system catalog in
  ``example/``. Differences, all documented upstream as supported settings:
  absolute paths into a per-instance writable copy of ``example/`` (the
  catalog store and sqlite need a writable directory and ``agent/`` is
  read-only), ``python_executor: local`` (no Docker daemon exists inside the
  Agent container; upstream itself falls back to local when Docker is
  unavailable), no ``embedding_model`` (upstream then uses its BM25 catalog
  retrieval; the shared ABB model provider exposes no embeddings endpoint)
  and ``report_directory`` inside the workspace. The chat model class and
  parameters are the example's ``langchain_openai.ChatOpenAI`` entry; the
  API key is not written into the YAML, ``ChatOpenAI`` reads the
  ``OPENAI_API_KEY`` the interception layer provides.

Session behaviour: ABB runs each Case input in a fresh oneshot worker, so
the in-memory checkpointer and long-term memory never span two inputs. An
``AskHuman`` interrupt inside one input is answered with the question text
the UI would show; there is no later input in the same process to resume it.

Input: text or exactly ``{"message": nonempty_text}``.
Config: the live ABB configuration is forwarded; upstream's own run
configuration (audit callback, user id, run name, metadata) is merged into
it without replacing ABB's thread id or callbacks.
Output: ``{"answer": str, "awaiting_user_input": bool}``; ``agent.toml``
extracts ``answer``.
Errors: invalid input, configuration and native failures propagate.
Ownership: the workspace directory and the compiled graph of this instance.
"""

from __future__ import annotations

import shutil
import tempfile
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_SOURCE_ROOT = Path(__file__).resolve().parents[1] / "agent"
_EXAMPLE_DIR = _SOURCE_ROOT / "example"
# Upstream's demo recording is not part of the deployment data.
_EXAMPLE_IGNORE = shutil.ignore_patterns("*.gif")
_USER_ID = "abb"


def _text_from_input(value: Any) -> str:
    if isinstance(value, Mapping):
        if set(value) != {"message"}:
            raise ValueError("Supply exactly one 'message' field")
        value = value["message"]
    if not isinstance(value, str) or not value.strip():
        raise ValueError("message must be a non-empty string")
    return value


def _deployment_config(workspace: Path) -> dict[str, Any]:
    """Upstream example/config.yaml, with absolute paths into the workspace."""
    example = workspace / "example"
    return {
        "organization": "MyCompany",
        "dialect": "sqlite",
        "bi_config_file": str(example / "bi.yaml"),
        "enable_sql_result_limit": True,
        "sql_result_limit": 10000,
        "enable_fail_closed_sql_guard": False,
        "python_executor": "local",
        "visualization_mode": "llm",
        "catalog_store": {"store_type": "file_system", "data_path": str(example)},
        "data_warehouse_config": {
            "uri": f"sqlite:///{example / 'tracking_orders.sqlite'}",
            "database_name": "",
        },
        "report_directory": str(workspace / "reports"),
        "default_llm": {
            "class": "langchain_openai.ChatOpenAI",
            "params": {"model": "gpt-5.5", "temperature": 0.01, "max_tokens": 8192},
        },
    }


class OpenChatBIGraph:
    def __init__(self) -> None:
        if not _EXAMPLE_DIR.is_dir():
            raise RuntimeError(f"Imported Agent example data not found at {_EXAMPLE_DIR}")
        self._workspace = Path(tempfile.mkdtemp(prefix="openchatbi-"))
        self._session_id = uuid.uuid4().hex
        self._graph = None
        try:
            shutil.copytree(_EXAMPLE_DIR, self._workspace / "example", ignore=_EXAMPLE_IGNORE)
            self._load_config()
            self._graph = self._build_graph()
        except BaseException:
            self.close()
            raise

    def _load_config(self) -> None:
        import yaml
        from openchatbi import config

        path = self._workspace / "config.yaml"
        path.write_text(yaml.safe_dump(_deployment_config(self._workspace), sort_keys=False), encoding="utf-8")
        config.load(str(path))

    @staticmethod
    def _build_graph():
        from langgraph.checkpoint.memory import MemorySaver
        from openchatbi import config
        from openchatbi.agent_graph import build_agent_graph_sync
        from openchatbi.tool.memory import get_sync_memory_store

        # run_cli.build_sync_graph(provider=None)
        return build_agent_graph_sync(
            config.get().catalog_store,
            checkpointer=MemorySaver(),
            memory_store=get_sync_memory_store(),
            llm_provider=None,
        )

    def _run_config(self, config: Any) -> dict[str, Any]:
        """Merge upstream's run configuration into ABB's without copying live objects."""
        from openchatbi.observability.tracing import build_run_config

        incoming = dict(config or {})
        configurable = dict(incoming.get("configurable") or {})
        thread_id = str(configurable.get("thread_id") or self._session_id)
        native = build_run_config(user_id=_USER_ID, session_id=thread_id)
        merged = dict(incoming)
        merged["configurable"] = {**native["configurable"], **configurable, "thread_id": thread_id}
        merged["callbacks"] = [*list(incoming.get("callbacks") or []), *native["callbacks"]]
        merged["metadata"] = {**native["metadata"], **dict(incoming.get("metadata") or {})}
        merged.setdefault("run_name", native["run_name"])
        return merged

    def invoke(self, value: Any, config: Any = None) -> dict[str, Any]:
        if self._graph is None:
            raise RuntimeError("Binding is closed")
        from openchatbi.utils import get_text_from_content

        text = _text_from_input(value)
        run_config = self._run_config(config)
        self._graph.invoke({"messages": [{"role": "user", "content": text}]}, config=run_config)
        # run_cli._handle_state: an interrupt shows the AskHuman question,
        # otherwise the final answer is the content of the last message.
        state = self._graph.get_state(run_config)
        if state.interrupts:
            payload = state.interrupts[0].value or {}
            question = str(payload.get("text") or "").strip()
            if not question:
                raise RuntimeError("Agent interrupted without a question for the user")
            return {"answer": question, "awaiting_user_input": True}
        messages = (state.values or {}).get("messages") or []
        if not messages:
            raise RuntimeError("Agent finished without any message")
        answer = get_text_from_content(messages[-1].content)
        if not isinstance(answer, str) or not answer.strip():
            raise RuntimeError("Agent returned no answer text")
        return {"answer": answer, "awaiting_user_input": False}

    def close(self) -> None:
        self._graph = None
        workspace, self._workspace = self._workspace, None
        if workspace is not None:
            shutil.rmtree(workspace, ignore_errors=True)


def create_graph():
    """Return a fresh binding; example input: {'message': 'How many orders were shipped last month?'}."""
    return OpenChatBIGraph()
