"""Reusable Agent session ownership for SDK workers.

The SDK worker and the Agent run in one container and one process. SDKs supply
invocation envelopes. This module owns request artifacts,
optional workspace replay and session cleanup, never SDK submission history or
judging.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from agentbench.sdk.common.artifacts import Artifacts
from .protocols import AgentExecutionSession


def capture_workspace_replay(root, *, secrets=()):
    """Open optional host-mounted replay without putting it in SDK evidence."""
    from agentbench.runtime.replay_lifecycle import ReplayCapture
    from agentbench.runtime.workspace_replay import REPLAY_MOUNT

    if Path(REPLAY_MOUNT).is_dir():
        return ReplayCapture(root, REPLAY_MOUNT, secrets=secrets)
    return None


class ManagedAgentSession:
    """An AgentExecutionSession with durable artifacts and owned cleanup.

    Production workers pass a LocalAgentSession; tests may inject any session
    implementing the same protocol. This owner closes it.
    """

    def __init__(self, *, output: Path, session: AgentExecutionSession, replay=None):
        self.files = Artifacts(Path(output))
        self.session = session
        self.replay = replay
        self.closed = False

    async def invoke(self, envelope: Mapping[str, object], output: Path) -> Mapping[str, object]:
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
            result = await self.session.invoke(request, output)
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


class LocalAgentSession:
    """Run the native Agent worker in this SDK process, inside the same container.

    KUMA requires the SDK and the Agent to share one Docker container. Each
    invocation leaves request.json, result.json and framework.jsonl in its step
    directory. One native Agent session is reused for every input of the Case.
    """

    def __init__(self, root, *, capture_directory=None, invoke=None):
        from agentbench.runtime.agentcontainer.session import AgentSession

        if invoke is None:
            from agentbench.runtime.agentcontainer.worker import execute as invoke
        self.root = Path(root)
        self._invoke = invoke
        self.session = AgentSession()
        # Agent-native OTel belongs beside the attempt's other evidence (otel/).
        self.session.capture_directory = Path(capture_directory) if capture_directory else None
        self.closed = False

    async def invoke(self, envelope: Mapping[str, object], output: Path) -> Mapping[str, object]:
        if self.closed:
            raise RuntimeError('Agent session is closed')
        output = Path(output)
        request = output / 'request.json'
        if not request.is_file():
            Artifacts(output).save('request.json', envelope)
        await self._invoke(self.root, request, output, session=self.session)
        result = json.loads((output / 'result.json').read_text(encoding='utf-8'))
        if result.get('run_id') != envelope['run_id']:
            raise ValueError('Agent result belongs to a different invocation')
        return result

    async def aclose(self) -> None:
        if self.closed:
            return
        self.closed = True
        await self.session.aclose()

    def snapshot(self) -> Mapping[str, object]:
        return self.session.snapshot()
