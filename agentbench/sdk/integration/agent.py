"""Reusable Agent session ownership for trusted SDK workers.

SDKs supply invocation envelopes and an EvidenceSink. This module owns request
artifacts, optional workspace replay and session cleanup, never SDK submission
history or judging.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from agentbench.sdk.common.artifacts import Artifacts
from .protocols import AgentExecutionSession, EvidenceSink


def capture_workspace_replay(root, *, secrets=()):
    """Open optional host-mounted replay without putting it in SDK evidence."""
    from agentbench.runtime.replay_lifecycle import ReplayCapture
    from agentbench.runtime.workspace_replay import REPLAY_MOUNT

    if Path(REPLAY_MOUNT).is_dir():
        return ReplayCapture(root, REPLAY_MOUNT, secrets=secrets)
    return None


class ManagedAgentSession:
    """An AgentExecutionSession with durable artifacts and owned cleanup.

    By default, use the isolated directory channel configured by the host's
    agent_timeout and agent_response_limits settings. An explicitly injected
    session implements the same protocol and is closed by this owner.
    """

    def __init__(self, *, output: Path, settings=None,
                 session: AgentExecutionSession | None = None, replay=None):
        self.files = Artifacts(Path(output))
        if session is None:
            from .channel import DirectoryAgentSession
            from .context import ResponseLimits

            settings = settings or {}
            session = DirectoryAgentSession(
                timeout=settings.get('agent_timeout', 2400),
                response_limits=ResponseLimits(**settings.get('agent_response_limits', {})))
        self.session = session
        self.replay = replay
        self.closed = False

    async def invoke(self, envelope: Mapping[str, object], output: Path,
                     evidence: EvidenceSink) -> Mapping[str, object]:
        if self.closed:
            raise RuntimeError('Managed Agent session is closed')
        output = Path(output)
        relative = output.resolve().relative_to(self.files.directory.resolve())
        self.files.save(str(relative / 'request.json'), envelope)
        # Persisted requests are redacted before crossing the Agent boundary,
        # exactly like the other public invocation artifacts.
        request = json.loads(Path(output / 'request.json').read_text(encoding='utf-8'))
        context = request.get('observation_context') or {}
        input_id = context.get('input_id')
        if self.replay is not None:
            self.replay.checkpoint('input_start', input_id)
        try:
            result = await self.session.invoke(request, output, evidence)
        finally:
            if self.replay is not None:
                self.replay.checkpoint('input_end', input_id)
        self.files.save(str(relative / 'result.json'), result)
        return json.loads(Path(output / 'result.json').read_text(encoding='utf-8'))

    async def aclose(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            await self.session.aclose()
        finally:
            try:
                self.files.save('session.json', self.snapshot())
            finally:
                if self.replay is not None:
                    self.replay.finish()

    def snapshot(self) -> Mapping[str, object]:
        return self.session.snapshot()

    async def __aenter__(self):
        if self.closed:
            raise RuntimeError('Managed Agent session is closed')
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        await self.aclose()


class InProcessAgentSession:
    """Explicit local/test adapter for the native Agent worker and its session.

    Production controller entrypoints require isolation. This adapter is only
    selected explicitly by callers that already own the in-process worker,
    trace provider and native session.
    """

    def __init__(self, root, *, provider, session, invoke):
        self.root = root
        self.provider = provider
        self.session = session
        self._invoke = invoke

    async def invoke(self, envelope: Mapping[str, object], output: Path,
                     evidence: EvidenceSink) -> Mapping[str, object]:
        # Local spans already reach the supplied provider directly; transported
        # spans and EvidenceSink are needed only for the isolated channel.
        Artifacts(output).save('request.json', envelope)
        await self._invoke(self.root, output / 'request.json', output,
                           provider=self.provider, session=self.session)
        return json.loads(Path(output / 'result.json').read_text(encoding='utf-8'))

    async def aclose(self) -> None:
        await self.session.aclose()

    def snapshot(self) -> Mapping[str, object]:
        return self.session.snapshot()
