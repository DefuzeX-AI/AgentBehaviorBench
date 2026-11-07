"""Run DeerFlow through its upstream embedded Python client.

Native entrypoint: ``deerflow.client.DeerFlowClient.chat``. This binding does
not start the Gateway, HTTP server, TUI, or a replacement graph. It constructs
the upstream embedded client with a real in-memory LangGraph checkpointer and a
stable per-instance thread id, then sends the current Case text to the native
chat method. The native client owns the lead agent, tools, middleware, skills,
artifact capture, and sandbox lifecycle.

Input: SDK text (a non-empty string), or exactly ``{"message": text}`` if a
mapping is supplied. No history is constructed here; reusing the binding keeps
the native thread/checkpoint session.
Config: forwarded through LangChain's ``set_config_context`` because the public
``chat`` method has no config parameter. This preserves live callbacks without
serializing them.
Output: the native answer string returned by ``DeerFlowClient.chat``.
Resources: one native client and one in-memory checkpointer per binding
instance. ``close``/``aclose`` drop the client and call its cleanup method when
available. The native stream's ``finally`` block owns sandbox lease cleanup.

Example input: ``"Summarize the latest advances in solid-state batteries."``
"""
from __future__ import annotations

import os
import uuid
from collections.abc import Mapping
from threading import RLock
from runtime_config import prepare_runtime_config


def _message_from_input(value):
    """Return one current text message from the SDK text boundary."""
    if isinstance(value, Mapping):
        if set(value) != {"message"}:
            raise ValueError(
                "DeerFlow accepts exactly one current text message; "
                "no other fields are supported"
            )
        value = value["message"]
    if not isinstance(value, str) or not value.strip():
        raise ValueError("DeerFlow requires non-empty text input")
    return value


class DeerFlowBinding:
    """Own one embedded DeerFlow client and its native session thread."""

    def __init__(self):
        self._client = None
        self._closed = False
        self._lock = RLock()
        self._thread_id = str(uuid.uuid4())

    def _load(self):
        if self._client is not None:
            return self._client
        prepare_runtime_config()
        from deerflow.client import DeerFlowClient
        from langgraph.checkpoint.memory import InMemorySaver

        self._client = DeerFlowClient(
            config_path=os.environ.get("DEER_FLOW_CONFIG_PATH") or None,
            checkpointer=InMemorySaver(),
        )
        return self._client

    def invoke(self, value, config=None):
        """Send the current text to DeerFlow's embedded client.

        Args:
            value: Non-empty SDK text or exactly ``{"message": text}``.
            config: LangChain RunnableConfig or None. It is applied through
                ``set_config_context`` around the native public call so live
                callbacks and metadata are not serialized or replaced.

        Returns:
            The native answer string from ``DeerFlowClient.chat``.

        Raises:
            ValueError: The input is not one non-empty text message.
            RuntimeError: This binding has already been closed.
            Exception: Native client, model, tool, and sandbox failures
                propagate unchanged.
        """
        message = _message_from_input(value)
        with self._lock:
            if self._closed:
                raise RuntimeError("DeerFlow binding is closed")
            client = self._load()
            from langchain_core.runnables.config import set_config_context

            run_config = dict(config or {})
            with set_config_context(run_config) as invocation_context:
                return invocation_context.run(
                    client.chat,
                    message,
                    thread_id=self._thread_id,
                    recursion_limit=run_config.get('recursion_limit', 100),
                )

    def close(self):
        """Drop the native client and call synchronous cleanup when present."""
        with self._lock:
            self._closed = True
            client, self._client = self._client, None
            if client is not None:
                close = getattr(client, "close", None)
                if callable(close):
                    close()

    async def aclose(self):
        """Async cleanup path; prefers native ``aclose`` when available."""
        with self._lock:
            self._closed = True
            client, self._client = self._client, None
            if client is None:
                return
            aclose = getattr(client, "aclose", None)
            if callable(aclose):
                await aclose()
                return
            close = getattr(client, "close", None)
            if callable(close):
                close()


def create_graph():
    """Return a fresh DeerFlow binding; example input: 'Research this topic.'"""
    return DeerFlowBinding()
