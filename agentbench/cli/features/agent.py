"""Agent source onboarding commands registered through the shared CLI router."""

from __future__ import annotations

import json
import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path

from agentbench.onboarding.source import AgentDownloadError, download_agent

from .base import CommandFeature
from .run import DEFAULT_REGISTRY_PATH


def configure_parser(parser: ArgumentParser) -> None:
    commands = parser.add_subparsers(dest="agent_command", required=True)
    add = commands.add_parser("add", help="Download an Agent and list files for onboarding.")
    add.add_argument("repository", help="HTTPS GitHub repository URL.")
    add.add_argument("--agents-dir", type=Path, default=DEFAULT_REGISTRY_PATH.parent / "agents",
                     help="Parent of numbered Agent folders (default: resources/agents).")
    add.set_defaults(agent_handler=_add)


def execute(args: Namespace) -> int:
    handler = getattr(args, "agent_handler", None)
    if not callable(handler):
        raise RuntimeError("No Agent command handler registered")
    try:
        return handler(args)
    except (AgentDownloadError, OSError) as exc:
        print(f"Agent add error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Agent download cancelled.", file=sys.stderr)
        return 130


def _add(args: Namespace) -> int:
    print("Downloading Agent source...", file=sys.stderr)
    result = download_agent(args.repository, args.agents_dir)
    print(f"Agent directory: {result.directory}", file=sys.stderr)
    print(f"Source revision: {result.revision}", file=sys.stderr)
    print("Files relative to agent/ (source downloaded; benchmark configuration pending):",
          file=sys.stderr)
    print(json.dumps(result.files, ensure_ascii=False, indent=2))
    return 0


FEATURE = CommandFeature(
    name="agent",
    help="Download and inspect Agent source for onboarding.",
    description="Prepare Agent source using numbered resource folders.",
    configure=configure_parser,
    execute=execute,
)
