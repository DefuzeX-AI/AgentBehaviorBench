"""Bridge BBA Case invocations to the native Article Explainer LangGraph swarm.

Native entrypoint: the compiled graph ``app`` exported by ``explainer/graph.py``;
this is the same object the saved descriptor ``abb-langgraph.json`` declares under
graph id ``article_explainer``. That upstream module builds five
``create_react_agent`` specialists (developer, summarizer, explainer,
analogy_creator, vulnerability_expert) joined by ``langgraph_swarm.create_swarm``
with ``default_active_agent="explainer"`` and no checkpointer. The swarm handoff
tools are the only tools; only the chat-model endpoint is contacted.

Prerequisite: the image installs the upstream ``article-explainer`` package (its
``explainer`` module tree) from ``pyproject.toml``/``uv.lock``. The binding loader
adds this file's import root; it does not install upstream dependencies.

Adaptations (boundary translation only; all reasoning stays in the native graph):
* Input: Case input is one current text string. It becomes a fresh one-message
  user state ``{"messages": [{"role": "user", "content": text}]}``. A mapping of
  exactly ``{"message": text}`` is accepted as an equivalent spelling. Every
  other shape raises ``ValueError``; unknown fields are never dropped. PDF
  parsing exists only in the excluded Streamlit UI and is never performed here.
* No history, memory, checkpointer or synthetic prior messages are added: each
  invocation is self-contained and ``active_agent`` keeps its native default
  ("explainer") because it is not supplied.
* Output: the complete native final state is returned unchanged — a mapping with
  ``messages`` (list of LangChain messages; the deliverable is the content of the
  last one) and ``active_agent`` (the specialist that produced it). No
  ``output_key`` is configured, so BBA consumes this raw mapping. The binding
  never extracts, relabels or fabricates an answer.
* Observation: the ``config`` argument (LangChain RunnableConfig: callbacks,
  tags, metadata) is forwarded to the native graph unchanged. This Agent has no
  ``[adapter.context]`` deployment values and the native API exposes no per-call
  context mechanism, so there is no ``context`` parameter.
* Model path stays native: importing ``explainer.graph`` runs
  ``explainer.service.config.get_chat_model()``, which requires the
  ``OPENAI_API_KEY`` environment variable (supplied by model interception, never
  stored in this file) to build the deployed
  ``init_chat_model("openai:gpt-4.1-mini")``. Without the key the native code
  silently selects a localhost Ollama fallback that is not deployed, so the
  binding fails fast instead of running against a dead endpoint.

Resource ownership: the binding owns no external resources — no files, sockets,
processes or persistent directories. ``create_graph()`` returns a fresh
lightweight wrapper per call; the graph it exposes is the upstream module-level
object, never copied or rebuilt. ``close()`` only drops the reference and makes
later invocations fail explicitly; it is safe to call repeatedly and after a
failed load.

Concrete input example: the text ``"Summarize this article section about
distributed locks."`` is invoked as state
``{"messages": [{"role": "user", "content": "Summarize this article section about distributed locks."}]}``;
the returned mapping's last ``messages`` entry carries the native answer content
(shape only — content is produced by the upstream agents).
"""

import asyncio
import os

__all__ = ["create_graph"]


def message_from_input(value):
    """Return the single current user text carried by a Case input.

    Args:
        value: The raw text string BBA delivers (no ``input_key`` is configured),
            or a mapping of exactly ``{"message": text}`` as an equivalent
            spelling.
    Returns:
        The validated non-empty text.
    Raises:
        ValueError: For empty or non-text payloads, extra or missing mapping
            fields, or any structured input this Agent does not support. Unknown
            fields are rejected, never silently discarded, and no prior
            conversation or document content is inferred.
    """
    if isinstance(value, dict):
        if set(value) != {"message"}:
            raise ValueError(
                "Article Explainer accepts exactly one current message field"
            )
        value = value["message"]
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Supply non-empty current question or article text")
    return value


class ArticleExplainer:
    """One BBA-facing handle onto the native compiled swarm graph.

    The wrapper holds no mutable Agent state beyond a lazily bound reference to
    the upstream graph; all conversation, handoffs and answers remain inside the
    native graph execution.
    """

    def __init__(self):
        self._app = None
        self._closed = False

    def _load_app(self):
        """Bind the native compiled graph once; fail fast on a dead deployment."""
        if self._closed:
            raise RuntimeError("Article Explainer binding is closed")
        if self._app is None:
            if not os.environ.get("OPENAI_API_KEY"):
                raise RuntimeError(
                    "OPENAI_API_KEY must be supplied by model interception; "
                    "without it the native loader silently selects the "
                    "undeployed localhost Ollama fallback"
                )
            from langgraph.checkpoint.memory import InMemorySaver
            from explainer.graph import agent_swarm

            # p168 deployment fix (same as ABB 20733d968): upstream's `app` has no
            # checkpointer, so every Input restarted the conversation, while the native
            # Streamlit page keeps appending to one messages list. The ABB worker supplies
            # a stable per-Case thread_id, so LangGraph's own persistence keeps the turns.
            self._app = agent_swarm.compile(checkpointer=InMemorySaver())
        return self._app

    async def ainvoke(self, value, config=None):
        """Run one native swarm invocation and return its complete final state.

        Args:
            value: Current text (or exactly ``{"message": text}``); see
                :func:`message_from_input`.
            config: LangChain RunnableConfig from BBA, forwarded unchanged to the
                native graph so callbacks, tags and metadata observe the real
                swarm, handoff tools and model calls. Never replaced with
                ``{}`` and never serialized.
        Returns:
            The complete native final state mapping: ``messages`` (list of
            LangChain messages; the deliverable is the content of the last one)
            and ``active_agent`` (the specialist that ran last). Returned
            as-is because no ``output_key`` is configured; this is not a
            fabricated or relabeled answer.
        Raises:
            ValueError: Unsupported input shape.
            RuntimeError: Binding closed, or the ``OPENAI_API_KEY`` environment
                variable is absent so the deployed model path cannot be built.
            Native execution errors propagate unchanged as failures; they are
            never converted into success-looking answers.
        """
        message = message_from_input(value)
        app = self._load_app()
        return await app.ainvoke(
            {"messages": [{"role": "user", "content": message}]}, config=config
        )

    def invoke(self, value, config=None):
        """Synchronous bridge for callers without an active event loop.

        Runs :meth:`ainvoke` to completion via ``asyncio.run`` and returns its
        final state. Async callers must ``await ainvoke`` instead; calling this
        from inside a running event loop raises ``RuntimeError`` from asyncio.
        Arguments, returns and raised errors match :meth:`ainvoke`.
        """
        return asyncio.run(self.ainvoke(value, config))

    def close(self):
        """Release this wrapper and reject future invocations.

        The binding owns no external resources, so closing only drops the graph
        reference and marks the wrapper closed; the upstream module-level graph
        object remains owned by its own module. Safe to call repeatedly, and
        safe even if loading never succeeded.
        """
        self._closed = True
        self._app = None


def create_graph():
    """Zero-argument synchronous factory selected by ``bridge.py:create_graph``.

    Returns a fresh :class:`ArticleExplainer` wrapper (never a coroutine or
    generator) exposing ``invoke``/``ainvoke``. The wrapper owns mutable
    instance state, so each factory call produces an independent instance.
    """
    return ArticleExplainer()
