"""ABB binding for Yanyutin753/LambChat (QuickAgent).

Upstream exposes three LangGraph agents (search / quick / team). This deployment
runs only the native ``quick`` agent: START -> quick_agent_node -> END, a single
LLM turn with no tools, sandbox, or search handoff.

MongoDB, Redis, Postgres checkpoints, MCP, Daytona/E2B sandboxes, and the
FastAPI/frontend surfaces stay out of scope. The binding forces an in-memory
checkpointer and injects ABB interceptor credentials through
``agent_options._resolved_model_config`` so ``LLMClient.get_model`` never hits
LambChat's model storage.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path
from typing import Any

_UNIT_ROOT = Path(__file__).resolve().parents[1]
_SOURCE_ROOT = _UNIT_ROOT / "agent"


def _prepare_runtime_env() -> None:
    """Prefer MemorySaver and avoid waiting on local Mongo/Redis."""

    os.environ.setdefault("CHECKPOINT_BACKEND", "disabled")
    # Unreachable endpoints: storage clients must not block Case startup.
    # QuickAgent.initialize is overridden to skip checkpointer factories.
    os.environ.setdefault("MONGODB_URL", "mongodb://127.0.0.1:1")
    os.environ.setdefault(
        "MONGODB_SERVER_SELECTION_TIMEOUT_MS",
        "500",
    )
    os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:1/0")


def _prepare_import_path() -> None:
    path = str(_SOURCE_ROOT.resolve())
    if path not in sys.path:
        sys.path.insert(0, path)


def _install_optional_stubs() -> None:
    """Keep Postgres/checkpoint optional stacks from loading on import.

    ``src.infra.storage`` eagerly imports ``postgres`` (PostgresStore). QuickAgent
    never needs it under ABB, so stub the missing langgraph store module instead
    of installing psycopg + langgraph-checkpoint-postgres.
    """

    import types

    def _ensure(name: str) -> types.ModuleType:
        if name in sys.modules:
            mod = sys.modules[name]
        else:
            mod = types.ModuleType(name)
            # Namespace packages so ``from pkg.sub import x`` can resolve stubs.
            mod.__path__ = []  # type: ignore[attr-defined]
            sys.modules[name] = mod
        if "." in name:
            parent_name, _, child = name.rpartition(".")
            parent = _ensure(parent_name)
            setattr(parent, child, mod)
        return mod

    for name in (
        "psycopg",
        "psycopg.rows",
        "psycopg_pool",
        "langgraph.store.postgres",
        "langgraph.checkpoint.postgres",
        "langgraph.checkpoint.postgres.aio",
        "langgraph.checkpoint.mongodb",
        "daytona",
        "e2b",
        "cubesandbox",
        "arq",
        "arq.constants",
        "arq.jobs",
        "arq.utils",
        "arq.worker",
        "arq.connections",
        "arq.typing",
        "minio",
        "oss2",
        "boto3",
        "botocore",
        "qdrant_client",
        "lark_oapi",
        "trafilatura",
        "markitdown",
        "pywebpush",
        "jieba",
        "jieba.posseg",
        "pypinyin",
    ):
        _ensure(name)

    # Minimal jieba.posseg surface used by memory classification/summaries.
    posseg = sys.modules["jieba.posseg"]

    def _cut(text, *_a, **_k):
        for token in str(text or "").split():
            yield types.SimpleNamespace(word=token, flag="n")

    posseg.cut = _cut  # type: ignore[attr-defined]
    sys.modules["pypinyin"].Style = types.SimpleNamespace(NORMAL=0)  # type: ignore[attr-defined]
    sys.modules["pypinyin"].lazy_pinyin = lambda text, **_k: list(str(text))  # type: ignore[attr-defined]

    postgres = sys.modules["langgraph.store.postgres"]

    class _PostgresStore:
        @classmethod
        def from_conn_string(cls, *_a, **_k):
            raise RuntimeError("PostgresStore is disabled in this ABB deployment")

    postgres.PostgresStore = _PostgresStore  # type: ignore[attr-defined]

    # daytona SDK surface imported by sandbox helpers (unused under QuickAgent).
    daytona = sys.modules["daytona"]

    class _DaytonaDisabled:
        def __init__(self, *_a, **_k):
            raise RuntimeError("Daytona sandbox is disabled in this ABB deployment")

    for _name in (
        "FileDownloadRequest",
        "FileUpload",
        "AsyncDaytona",
        "Daytona",
        "DaytonaConfig",
        "CreateSandboxFromSnapshotParams",
    ):
        setattr(daytona, _name, type(_name, (_DaytonaDisabled,), {}))

    class _Subscriptable:
        def __class_getitem__(cls, _item):
            return cls

    class _Connection(_Subscriptable):
        pass

    class _ConnectionPool(_Subscriptable):
        def __init__(self, *_a, **_k):
            pass

    psycopg = sys.modules["psycopg"]
    psycopg.Connection = _Connection  # type: ignore[attr-defined]
    sys.modules["psycopg.rows"].dict_row = object()  # type: ignore[attr-defined]
    sys.modules["psycopg_pool"].ConnectionPool = _ConnectionPool  # type: ignore[attr-defined]


def _model_config() -> dict[str, Any]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for ABB model interception")
    model = os.environ.get("OPENAI_MODEL", "deepseek-chat")
    return {
        "value": model,
        "label": "ABB intercepted model",
        "provider": "openai",
        "api_key": api_key,
        "api_base": os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1",
        "api_format": "chat_completions",
        "enabled": True,
        "temperature": float(os.environ.get("ABB_LAMBCHAT_TEMPERATURE", "0.2")),
    }


class _LambChatQuickAgent:
    """Sync factory result exposing invoke/ainvoke over native QuickAgent."""

    def __init__(self) -> None:
        self._agent = None
        self._thread = 0

    def _ensure_agent(self):
        if self._agent is not None:
            return self._agent

        _prepare_runtime_env()
        _prepare_import_path()
        _install_optional_stubs()

        from langgraph.checkpoint.memory import MemorySaver

        from src.agents.core.base import GraphBuilder
        from src.agents.quick_agent.graph import QuickAgent
        from src.infra.llm.quota import QuotaChatMixin

        # ABB Cases have no LambChat user ledger / Mongo budgets. Skip metering
        # so LLMClient can call the intercepted OpenAI-compatible endpoint.
        async def _abb_quota_begin(self, messages, kwargs):
            del self, messages, kwargs
            return None

        async def _abb_quota_finish(self, *args, **kwargs):
            del self, args, kwargs
            return None

        QuotaChatMixin._quota_begin = _abb_quota_begin  # type: ignore[method-assign]
        QuotaChatMixin._quota_finish = _abb_quota_finish  # type: ignore[method-assign]

        class AbbQuickAgent(QuickAgent):
            """Same graph as upstream; MemorySaver only (no Mongo/PG)."""

            async def initialize(self) -> None:
                if self._initialized:
                    return
                self._checkpointer = MemorySaver()
                builder = GraphBuilder(self.state_class)
                self.build_graph(builder)
                self._graph = builder.compile(
                    checkpointer=self._checkpointer,
                    recursion_limit=self.recursion_limit,
                )
                self._initialized = True

        self._agent = AbbQuickAgent(enable_checkpointer=True)
        return self._agent

    def _message(self, value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            if "input" in value and isinstance(value["input"], str):
                return value["input"]
            if "message" in value:
                return str(value["message"])
            messages = value.get("messages")
            if isinstance(messages, list) and messages:
                last = messages[-1]
                if isinstance(last, str):
                    return last
                if isinstance(last, tuple) and len(last) >= 2:
                    return str(last[1])
                content = getattr(last, "content", None)
                if content is not None:
                    return str(content)
                if isinstance(last, dict):
                    return str(last.get("content") or last.get("text") or last)
        raise TypeError("LambChat QuickAgent expects a text message or {input/messages/...}")

    def _config(self, config: dict | None) -> dict:
        self._thread += 1
        thread_id = f"abb-lambchat-{self._thread}"
        merged = dict(config or {})
        configurable = dict(merged.get("configurable") or {})
        configurable["thread_id"] = str(configurable.get("thread_id") or thread_id)
        # Key present with None skips DB fallback lookup inside quick_agent_node.
        configurable["agent_options"] = {
            "model": os.environ.get("OPENAI_MODEL", "deepseek-chat"),
            "_resolved_model_config": _model_config(),
            "_resolved_fallback_model": None,
            "enable_thinking": "off",
        }
        configurable["allow_search_handoff"] = False
        merged["configurable"] = configurable
        return merged

    async def ainvoke(self, value: Any, config: dict | None = None, **kwargs):
        del kwargs
        agent = self._ensure_agent()
        if not agent._initialized:
            await agent.initialize()

        message = self._message(value)
        session_id = str(
            (config or {}).get("configurable", {}).get("thread_id")
            or uuid.uuid4()
        )
        run_config = self._config(config)
        run_config["configurable"]["thread_id"] = session_id
        run_config["recursion_limit"] = agent.recursion_limit

        result = await agent._graph.ainvoke(
            {
                "input": message,
                "session_id": session_id,
                "messages": [],
                "output": "",
                "attachments": None,
            },
            config=run_config,
        )
        output = result.get("output") or ""
        return {"output": output, "messages": result.get("messages") or []}

    def invoke(self, value: Any, config: dict | None = None, **kwargs):
        return asyncio.run(self.ainvoke(value, config=config, **kwargs))


def create_graph():
    """Synchronous factory required by ABB LangGraph adapters."""

    return _LambChatQuickAgent()
