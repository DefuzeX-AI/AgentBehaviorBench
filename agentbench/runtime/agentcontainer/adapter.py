"""AgentAdapter implementation backed by an isolated runtime session."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from agentbench.adapter import AdapterInvocation, AgentDescriptor
from agentbench.runtime.contracts import AgentRuntime, RuntimeSession

ContainerCaller = Callable[[RuntimeSession, object, object | None], AdapterInvocation]


class ContainerAgentAdapter:
    def __init__(
        self, agent: AgentDescriptor, runtime: AgentRuntime,
        *, caller: ContainerCaller | None = None,
    ) -> None:
        self._agent = agent
        self._runtime = runtime
        self._session: RuntimeSession | None = None
        self._caller = caller

    @property
    def is_loaded(self) -> bool:
        return self._session is not None and self._session.is_running

    def load(self) -> "ContainerAgentAdapter":
        if self._session is None:
            self._session = self._runtime.start(self._agent)
        return self

    def invoke(
        self, value: object, *, run_config: object | None = None
    ) -> AdapterInvocation:
        if self._caller is None:
            raise RuntimeError(
                "No native Agent caller configured. Start the runtime directly to "
                "manage its process, or supply a caller for the Agent's API."
            )
        session = self._require_session()
        checkpoint_fn = getattr(session, "trace_checkpoint", None)
        checkpoint = checkpoint_fn() if callable(checkpoint_fn) else None
        result = self._caller(session, value, run_config)
        validate = getattr(session, "validate_trace", None)
        if callable(validate):
            validate(checkpoint)
        return result

    async def ainvoke(
        self, value: object, *, run_config: object | None = None
    ) -> AdapterInvocation:
        return await asyncio.to_thread(self.invoke, value, run_config=run_config)

    def close(self) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None

    def _require_session(self) -> RuntimeSession:
        if self._session is None:
            self.load()
        if self._session is None:  # pragma: no cover - defensive guard
            raise RuntimeError("Container runtime did not create a session")
        return self._session
