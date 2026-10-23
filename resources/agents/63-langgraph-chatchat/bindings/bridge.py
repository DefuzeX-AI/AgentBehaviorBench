"""ABB binding for chatchat-space/LangGraph-Chatchat.

Upstream keeps a graph registry of RAG and agent workflows. This deployment
exposes only the native ``base_agent`` (聊天机器人) graph: history_manager →
chatbot → optional tools → chatbot. Tools are empty so Cases stay plain-text
chat. Streamlit/WebUI, Xinference, knowledge bases, SQL, internet search and
postgres/sqlite checkpoints are out of scope.

Upstream ``agent/`` is unchanged. Heavy optional stacks are stubbed before
import so the container stays within a practical dependency budget.
"""

from __future__ import annotations

import asyncio
import os
import sys
import types
from pathlib import Path
from typing import Any


_UNIT_ROOT = Path(__file__).resolve().parents[1]
_SOURCE_ROOT = _UNIT_ROOT / "agent" / "chatchat-server"
_DATA_ROOT = _UNIT_ROOT / "install" / "chatchat_data"


def _ensure_chatchat_root() -> Path:
    root = Path(os.environ.get("CHATCHAT_ROOT") or _DATA_ROOT).resolve()
    root.mkdir(parents=True, exist_ok=True)
    (root / "data").mkdir(parents=True, exist_ok=True)
    os.environ["CHATCHAT_ROOT"] = str(root)
    return root


def _install_import_stubs() -> None:
    """Keep Streamlit / FastAPI / optional stacks from loading on import."""

    def _ensure(name: str) -> types.ModuleType:
        if name in sys.modules:
            return sys.modules[name]
        mod = types.ModuleType(name)
        sys.modules[name] = mod
        return mod

    for name in (
        "streamlit",
        "fastapi",
        "memoization",
        "nltk",
        "sse_starlette",
        "uvicorn",
        "elasticsearch",
        "faiss",
        "cv2",
        "unstructured",
        "xinference_client",
        "pymysql",
        "psycopg",
        "psycopg_pool",
        "langgraph.checkpoint.sqlite",
        "langgraph.checkpoint.sqlite.aio",
        "langgraph.checkpoint.postgres",
        "langgraph.checkpoint.postgres.aio",
    ):
        _ensure(name)

    streamlit = sys.modules["streamlit"]

    def _identity(fn=None, **_kwargs):
        if fn is None:
            return lambda inner: inner
        return fn

    streamlit.cache_data = _identity  # type: ignore[attr-defined]
    streamlit.cache_resource = _identity  # type: ignore[attr-defined]
    streamlit.session_state = {}  # type: ignore[attr-defined]

    fastapi = sys.modules["fastapi"]
    fastapi.FastAPI = type("FastAPI", (), {"__init__": lambda self, *a, **k: None})  # type: ignore[attr-defined]

    memo = sys.modules["memoization"]

    def cached(*_a, **_k):
        def wrap(fn):
            return fn

        return wrap

    memo.cached = cached  # type: ignore[attr-defined]
    memo.CachingAlgorithmFlag = types.SimpleNamespace(LRU=1)  # type: ignore[attr-defined]

    nltk = sys.modules["nltk"]
    nltk.data = types.SimpleNamespace(path=[])  # type: ignore[attr-defined]

    aio = sys.modules["langgraph.checkpoint.sqlite.aio"]

    class _AsyncSqliteSaver:
        @classmethod
        def from_conn_string(cls, *_a, **_k):
            raise RuntimeError("SQLite graph checkpoint is disabled in this ABB deployment")

    aio.AsyncSqliteSaver = _AsyncSqliteSaver  # type: ignore[attr-defined]


def _prepare_import_path() -> None:
    path = str(_SOURCE_ROOT.resolve())
    if path not in sys.path:
        sys.path.insert(0, path)


def _stub_server_utils() -> None:
    """Avoid importing the full chatchat.server.utils stack (FastAPI, embeddings…)."""

    name = "chatchat.server.utils"
    if name in sys.modules and hasattr(sys.modules[name], "build_logger"):
        return
    mod = types.ModuleType(name)

    def build_logger(*_a, **_k):
        import logging

        return logging.getLogger("chatchat.abb")

    mod.build_logger = build_logger  # type: ignore[attr-defined]
    sys.modules[name] = mod


def _load_base_agent_graph():
    """Import BaseAgentGraph without executing graphs_factory/__init__.py."""

    import importlib.util

    _stub_server_utils()
    factory_dir = _SOURCE_ROOT / "chatchat" / "server" / "agent" / "graphs_factory"
    package = "chatchat.server.agent.graphs_factory"
    if package not in sys.modules:
        pkg = types.ModuleType(package)
        pkg.__path__ = [str(factory_dir)]  # type: ignore[attr-defined]
        sys.modules[package] = pkg

    def _load(mod_name: str, file_name: str):
        full = f"{package}.{mod_name}"
        if full in sys.modules:
            return sys.modules[full]
        spec = importlib.util.spec_from_file_location(full, factory_dir / file_name)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load {full}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[full] = module
        spec.loader.exec_module(module)
        return module

    _load("graphs_registry", "graphs_registry.py")
    return _load("base_agent", "base_agent.py").BaseAgentGraph


def _openai_chat_model():
    from langchain_openai import ChatOpenAI

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for ABB model interception")
    return ChatOpenAI(
        model=os.environ.get("OPENAI_MODEL", "deepseek-chat"),
        temperature=float(os.environ.get("ABB_CHATCHAT_TEMPERATURE", "0.2")),
        api_key=api_key,
        base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    )


class _ChatchatBaseAgent:
    """Sync factory result exposing invoke/ainvoke over the native base_agent graph."""

    def __init__(self) -> None:
        self._graph = None
        self._thread = 0

    def _ensure_graph(self):
        if self._graph is not None:
            return self._graph
        _ensure_chatchat_root()
        _install_import_stubs()
        _prepare_import_path()

        from langgraph.checkpoint.memory import MemorySaver

        from chatchat.settings import Settings

        BaseAgentGraph = _load_base_agent_graph()
        history_len = int(getattr(Settings.model_settings, "HISTORY_LEN", 10) or 10)
        wrapper = BaseAgentGraph(
            llm=_openai_chat_model(),
            tools=[],
            history_len=history_len,
            checkpoint=MemorySaver(),
        )
        self._graph = wrapper.get_graph()
        return self._graph

    def _normalize(self, value: Any) -> dict[str, Any]:
        from langchain_core.messages import HumanMessage

        if isinstance(value, dict) and "messages" in value:
            messages = value["messages"]
            if messages and isinstance(messages[0], tuple):
                messages = [
                    HumanMessage(content=str(item[1])) if item[0] in {"user", "human"} else item
                    for item in messages
                ]
            return {**value, "messages": messages}
        if isinstance(value, str):
            return {"messages": [HumanMessage(content=value)]}
        if isinstance(value, dict) and "message" in value:
            return {"messages": [HumanMessage(content=str(value["message"]))]}
        raise TypeError("base_agent expects a text message or {messages: [...]}")

    def _config(self, config: dict | None) -> dict:
        self._thread += 1
        thread_id = f"abb-chatchat-{self._thread}"
        if config and isinstance(config.get("configurable"), dict):
            thread_id = str(config["configurable"].get("thread_id") or thread_id)
        return {"configurable": {"thread_id": thread_id}}

    @staticmethod
    def _text(result: dict[str, Any]) -> str:
        messages = result.get("messages") or []
        if not messages:
            return ""
        last = messages[-1]
        content = getattr(last, "content", last)
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                else:
                    parts.append(str(item))
            return "".join(parts)
        return str(content or "")

    async def ainvoke(self, value: Any, config: dict | None = None, **kwargs):
        del kwargs
        graph = self._ensure_graph()
        result = await graph.ainvoke(self._normalize(value), config=self._config(config))
        return {"messages": result.get("messages", []), "output": self._text(result)}

    def invoke(self, value: Any, config: dict | None = None, **kwargs):
        return asyncio.run(self.ainvoke(value, config=config, **kwargs))


def create_graph():
    """Synchronous factory required by ABB LangGraph adapters."""

    return _ChatchatBaseAgent()
