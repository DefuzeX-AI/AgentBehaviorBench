"""Agent unit commands registered through the shared CLI router."""

from __future__ import annotations

import sys
from argparse import ArgumentParser, Namespace

from ..base import CommandFeature
from . import add, delete


def configure_parser(parser: ArgumentParser) -> None:
    commands = parser.add_subparsers(dest="agent_command", required=True)
    add.configure_parser(commands)
    delete.configure_parser(commands)


def execute(args: Namespace) -> int:
    handler = getattr(args, "agent_handler", None)
    if not callable(handler):
        raise RuntimeError("No Agent command handler registered")
    try:
        return handler(args)
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"Agent {args.agent_command} error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print(getattr(args, "agent_interrupted", "Agent command cancelled."), file=sys.stderr)
        return 130


FEATURE = CommandFeature(
    name="agent",
    help="Import, inspect or delete Agent units.",
    description="Manage Agent units in numbered resource folders.",
    configure=configure_parser,
    execute=execute,
)
