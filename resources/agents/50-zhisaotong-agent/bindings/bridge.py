"""ABB boundary for bamboo-moon/zhisaotong-Agent (智扫通 robot-vacuum support Agent).

Native entrypoint
-----------------
``app.py`` is only the Streamlit front end. The application logic is
:class:`agent.react_agent.ReactAgent`, a LangChain ``create_agent`` ReAct graph
(``langgraph`` underneath) built from ``prompts/main_prompt.txt`` with seven
tools and three middlewares. ``app.py`` drives it through
``ReactAgent.execute_stream(query)``, a generator that wraps
``agent.stream(..., stream_mode="values")`` and yields the newest message text
after every stream step, so the last yielded value is the final assistant answer.

This binding invokes the same compiled graph (``ReactAgent().agent``) with
``ainvoke`` instead of consuming the stream generator, because ``execute_stream``
takes no ``RunnableConfig``: invoking the graph directly is what lets ABB's
callbacks, tags and thread settings reach the native model, tool and middleware
calls. ``agent/react_agent.py`` passes ``context={"report": False}``, and the
``report_prompt_switch`` middleware reads exactly that flag, so the binding
supplies the same runtime context. Reasoning, prompts, tools and middleware all
remain upstream code; no upstream file is modified.

Adaptations required by this deployment
---------------------------------------
1. **Model clients.** ``model/factory.py`` builds its clients at import time:
   ``ChatTongyi`` and ``DashScopeEmbeddings``. Both speak DashScope's native
   protocol, and ``ChatTongyi`` additionally needs a DashScope credential that
   this deployment deliberately does not use. ABB observes model traffic through
   its OpenAI-protocol interceptor (``agent.toml`` ``[[llm_interception.routes]]``),
   so the binding supplies a ``model.factory`` module exposing the two names the
   Agent imports — ``chat_model`` and ``embed_model`` — as OpenAI-compatible
   clients whose ``base_url`` is ``https://api.openai.com/v1``. Model interception
   replaces every request with the configured run model, so the Agent's behaviour
   follows the benchmark's model, not a hard-coded vendor. Prompts, tools and
   middleware are untouched.

2. **Knowledge base.** ``chroma_db/chroma.sqlite3`` in the upstream commit holds
   the ``agent`` collection but **zero** embeddings, while ``md5.text`` already
   records the MD5 of all six source documents. Upstream
   ``VectorStoreService.load_document()`` therefore skips every file and the
   retriever returns nothing. The binding rebuilds the index once, into its own
   temporary directory, so the Agent's retrieval is the behaviour its README
   documents. The embedder is a CPU-only local ONNX model baked into the image,
   which keeps the Agent self-contained: no second hosted model, no extra
   credential and no additional egress are required to answer product questions.
   ``docs/``-level detail: the model identity is recorded in ``requirement.md``.

3. **Amap tools keep upstream behaviour.** ``get_weather`` and
   ``get_user_location`` need an Amap web-service key and egress to
   ``restapi.amap.com``. This deployment provides neither, and ``config/agent.yml``
   still carries the upstream placeholder key. The upstream implementation already
   converts those failures into the Chinese error strings it hands back to the
   model, so the tools stay enabled and degrade exactly as written.

Input example: ``"扫地机器人的滤网多久需要更换一次？"``
Output shape: ``{"answer": "<final assistant text>"}`` — never a fabricated answer;
native execution errors and an empty final assistant turn propagate as failures.
"""

from __future__ import annotations

import asyncio
import os
import sys
import types
from collections.abc import Mapping, Sequence
from pathlib import Path
from tempfile import TemporaryDirectory

from langchain_core.embeddings import Embeddings

# ``resources/agents/NN-zhisaotong-agent/agent/`` is the upstream repository root.
SOURCE_ROOT = Path(__file__).resolve().parent.parent / "agent"

# The host whose OpenAI-protocol endpoints agent.toml declares to the interceptor.
# Model interception rewrites both requests to the configured run model.
INTERCEPTED_BASE_URL = "https://api.openai.com/v1"

# Deployment defaults. Kept in the binding so no upstream file is edited.
CHAT_MODEL_NAME = os.environ.get("ABB_CHAT_MODEL_NAME", "gpt-4.1-mini")
RAG_EMBEDDING_MODEL = os.environ.get("ABB_RAG_EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")


def _prepend_source_root() -> None:
    """Make the upstream top-level packages (agent, model, rag, utils) importable."""
    root = str(SOURCE_ROOT)
    if not SOURCE_ROOT.is_dir():
        raise RuntimeError(f"Upstream source directory is missing: {SOURCE_ROOT}")
    if root not in sys.path:
        sys.path.insert(0, root)


class _LocalEmbeddings(Embeddings):
    """LangChain ``Embeddings`` adapter over the CPU-only ONNX model in the image.

    Used only to build the Agent's local Chroma index. Keeping the embedder
    in-image is what makes the RAG tool self-contained: no second hosted model,
    no extra credential and no additional egress.

    Subclasses ``langchain_core.embeddings.Embeddings`` rather than duck-typing so
    that ``langchain_chroma.Chroma`` and any retriever wrapper recognise it.
    """

    def __init__(self, model_name: str) -> None:
        from fastembed import TextEmbedding

        self._model = TextEmbedding(model_name=model_name)

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [[float(value) for value in vector] for vector in self._model.embed(list(texts))]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def _install_model_clients() -> None:
    """Expose ``model.factory.chat_model`` / ``embed_model`` as intercepted clients.

    The Agent imports both names from ``model.factory`` at module import time, so
    the module must exist before ``agent.react_agent`` or ``rag.*`` is imported.
    Upstream ``model/factory.py`` constructs DashScope clients eagerly, which needs
    the DashScope credential this deployment does not use, so the binding replaces
    the module rather than editing it.
    """
    from langchain_openai import ChatOpenAI

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY must be supplied by model interception")

    factory = types.ModuleType("model.factory")
    factory.__doc__ = (
        "ABB deployment model clients. Replaces the upstream DashScope clients with "
        "OpenAI-protocol clients so that model interception observes every call. "
        "Supplied by bindings/bridge.py; no upstream file is modified."
    )
    factory.chat_model = ChatOpenAI(
        model=CHAT_MODEL_NAME, base_url=INTERCEPTED_BASE_URL, api_key=api_key, temperature=0.7
    )
    factory.embed_model = _LocalEmbeddings(RAG_EMBEDDING_MODEL)

    # ``model`` is a namespace package in the upstream layout; register the
    # replacement under both its attribute and the import system's cache.
    import model  # noqa: F401  (namespace package)

    sys.modules["model.factory"] = factory
    model.factory = factory  # type: ignore[attr-defined]


def _build_knowledge_index(workspace: Path) -> None:
    """Build the Chroma index the upstream commit ships without embeddings.

    ``chroma_conf`` is redirected to the binding's own writable workspace before
    ``rag.*`` is imported, and ``md5_hex_store`` points at a fresh file so the six
    recorded hashes in the upstream ``md5.text`` do not suppress indexing.
    """
    from utils import config_handler

    chroma_conf = config_handler.chroma_conf
    chroma_conf["persist_directory"] = str(workspace / "chroma_db")
    chroma_conf["md5_hex_store"] = str(workspace / "md5.text")

    from rag.vector_store import VectorStoreService

    VectorStoreService().load_document()


def _final_answer_text(state: object) -> str:
    """Return the newest assistant text, mirroring what execute_stream yields last."""
    from langchain_core.messages import AIMessage

    messages = state.get("messages") if isinstance(state, Mapping) else None
    if not isinstance(messages, (list, tuple)) or not messages:
        raise RuntimeError("Agent produced no messages")
    last = messages[-1]
    if not isinstance(last, AIMessage) or last.tool_calls:
        raise RuntimeError("Agent stopped without a final assistant response")
    content = last.content
    if isinstance(content, str):
        text = content
    elif isinstance(content, (list, tuple)):
        text = "".join(
            part.get("text", "") if isinstance(part, Mapping) else str(part) for part in content
        )
    else:
        text = ""
    if not text.strip():
        raise RuntimeError("Agent returned an empty final response")
    return text.strip()


class ZhisaotongGraph:
    """Drive the upstream ReAct Agent for one ABB Input.

    ``invoke``/``ainvoke`` accept the prepared Case input as plain text, or as a
    mapping whose ``message`` field carries that text. They return
    ``{"answer": <final assistant text>}``. The native graph result is not exposed
    because ``agent.toml`` sets ``output_key = "answer"``.

    Resources owned here: one temporary workspace holding the rebuilt Chroma index
    and the run's MD5 ledger, plus the log directory the upstream logger writes to.
    Both are released by ``close()``, which is safe to call repeatedly and also
    after a partially failed initialization.
    """

    def __init__(self) -> None:
        self._workspace: TemporaryDirectory[str] | None = None
        self._agent: object | None = None

    def _load(self) -> object:
        if self._agent is not None:
            return self._agent
        workspace = TemporaryDirectory(prefix="abb-zhisaotong-")
        self._workspace = workspace
        try:
            _prepend_source_root()
            _install_model_clients()
            _build_knowledge_index(Path(workspace.name))
            from agent.react_agent import ReactAgent

            self._agent = ReactAgent()
        except BaseException:
            self.close()
            raise
        return self._agent

    @staticmethod
    def _question(value: object) -> str:
        """Accept the Case text, or a mapping carrying exactly one message field."""
        if isinstance(value, Mapping):
            if set(value) != {"message"}:
                raise ValueError("Supply the Case Input as text, or exactly {'message': text}")
            value = value["message"]
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Case Input must be non-empty text")
        return value

    async def ainvoke(self, value: object, config: object = None, *, context: object = None) -> dict:
        """Run the native graph once and return its final assistant answer.

        Args:
            value: The Case Input as text, or ``{"message": <text>}``.
            config: Process-local LangChain ``RunnableConfig`` from ABB, forwarded
                unchanged so callbacks, tags, metadata and thread settings reach
                the native model, tool and middleware calls.
            context: Not used. ``agent.toml`` declares no ``[adapter.context]``;
                the native runtime context the upstream app passes
                (``{"report": False}``) is supplied here so the report-prompt
                middleware behaves exactly as it does under ``app.py``.
        Returns:
            ``{"answer": <final assistant text>}``.
        Raises:
            ValueError: The Case Input is not usable text.
            RuntimeError: The Agent stopped without a final assistant response, or
                returned an empty one. Native execution errors propagate unchanged.
        """
        question = self._question(value)
        agent = self._load()
        state = await agent.agent.ainvoke(
            {"messages": [{"role": "user", "content": question}]},
            config=config,
            context={"report": False},
        )
        return {"answer": _final_answer_text(state)}

    def invoke(self, value: object, config: object = None, *, context: object = None) -> dict:
        """Synchronous form of :meth:`ainvoke`, for callers without an event loop."""
        return asyncio.run(self.ainvoke(value, config, context=context))

    def close(self) -> None:
        """Release the owned workspace; safe to repeat and after a partial load."""
        agent, self._agent = self._agent, None
        workspace, self._workspace = self._workspace, None
        try:
            if agent is not None:
                closer = getattr(agent, "close", None)
                if callable(closer):
                    closer()
        finally:
            if workspace is not None:
                workspace.cleanup()


def create_graph() -> ZhisaotongGraph:
    """Return a fresh binding instance for one ABB Case."""
    return ZhisaotongGraph()
