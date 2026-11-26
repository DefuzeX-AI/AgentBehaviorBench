"""Serve the turns of one chat in a single Agent session inside the container.

The one-shot worker answers one input and exits. This entry keeps one
AgentSession open across turns, so the Agent owns its conversation history the
same way it does across the Inputs of an SDK Case. Each turn goes through the
same worker ``execute`` call and leaves request.json, result.json and framework
evidence in ``steps/NNNN/``; Agent-native OTel lands in the shared ``otel/``.
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from uuid import uuid4

from agentbench.observe.store import atomic_json, environment_secrets, redact
from . import mailbox


async def serve(root, inbox, output, *, session_id, session=None, invoke=None,
                publish=None, poll=0.2):
    """Answer turn files in order until the host posts the end marker.

    Args:
        root: Agent unit directory with its manifest and native entrypoint.
        inbox: Read-only mailbox directory the host writes turn files into.
        output: Writable attempt directory receiving steps/ and otel/.
        session_id: Stable Agent session identity shared by every turn.
        session, invoke, publish: Test seams for the AgentSession, the worker
            ``execute`` call and the host-read permission publication.
    Returns:
        Zero after the end marker; turn failures stay in their result.json.
    """
    root, inbox, output = Path(root), Path(inbox), Path(output)
    from .config import tomllib
    manifest = tomllib.loads((root / "agent.toml").read_text(encoding="utf-8"))
    if session is None:
        from .session import AgentSession
        session = AgentSession()
        session.capture_directory = output / "otel"
    if invoke is None:
        from .worker import execute as invoke
    if publish is None:
        from agentbench.sdk.common.output_permissions import share_output as publish
    secrets = environment_secrets()
    number = 1
    try:
        while True:
            request = mailbox.turn_path(inbox, number)
            while not request.is_file():
                if mailbox.end_path(inbox).is_file():
                    return 0
                await asyncio.sleep(poll)
            value = mailbox.read_turn(request, number)
            folder = mailbox.step_directory(output, number)
            folder.mkdir(parents=True)
            input_id = mailbox.turn_name(number)
            envelope = {"schema": "abb.invocation.v1", "run_id": uuid4().hex, "session_id": session_id,
                        "observation_context": {"input_id": input_id},
                        "agent_id": manifest["agent_id"], "framework": manifest["framework"],
                        "input": value["input"]}
            # input.json is the recorded Input of a step; trajectory readers take user turns from it.
            atomic_json(folder / "input.json", redact({"input_id": input_id, "payload": value["input"]}, secrets))
            atomic_json(folder / "request.json", redact(envelope, secrets))
            await invoke(root, folder / "request.json", folder, session=session)
            # Atomic writes are owner-only; the host reads each answer while the chat runs.
            publish(folder)
            number += 1
    finally:
        try:
            await session.aclose()
        finally:
            publish(output)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent-root", type=Path, default=Path("/opt/agent"))
    parser.add_argument("--mailbox", type=Path, default=Path("/run/abb-input"))
    parser.add_argument("--output", type=Path, default=Path("/run/abb-output"))
    parser.add_argument("--session-id", required=True)
    args = parser.parse_args()
    # The worker's execute call configures interceptor trust for every turn.
    return asyncio.run(serve(args.agent_root.resolve(), args.mailbox, args.output,
                             session_id=args.session_id))


if __name__ == "__main__":
    raise SystemExit(main())
