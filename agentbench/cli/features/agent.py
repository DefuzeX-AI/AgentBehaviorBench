"""Agent source onboarding commands registered through the shared CLI router."""

from __future__ import annotations

import json
import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path

from agentbench.onboarding.source import download_agent

from .base import CommandFeature
from .run import DEFAULT_REGISTRY_PATH
from agentbench.cli.sdk import configure_sdk_parser


def configure_parser(parser: ArgumentParser) -> None:
    commands = parser.add_subparsers(dest="agent_command", required=True)
    add = commands.add_parser("add", help="Download an Agent and list files for onboarding.")
    add.add_argument("repository", help="HTTPS GitHub repository URL.")
    add.add_argument("--agents-dir", type=Path, default=DEFAULT_REGISTRY_PATH.parent / "agents",
                     help="Parent of numbered Agent folders (default: resources/agents).")
    add.add_argument("-b", "--build", action="store_true", help="Generate, validate and save files one at a time; resume valid files.")
    add.add_argument("-c", "--certify", action="store_true", help="Run existing certification using generated or manual files.")
    add.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    add.add_argument("--build-settings", type=Path, help="TOML [build] overrides for generation.")
    add.add_argument("--build-model", help="OpenRouter model for configuration generation only.")
    add.add_argument("--answers", type=Path, help="Text answers to a previous build plan's questions.")
    add.add_argument("--with-observe", action="store_true", help="With -b, generate Observe fields from the input definition.")
    add.add_argument("--agent-timeout", type=float, help="With -b, override the generated Agent timeout (default: 300 seconds).")
    add.add_argument("--adapter-context", type=Path, help="With -b, explicit deployment overrides as a JSON object; omitted by default.")
    add.add_argument("--env-file", type=Path, help="Host environment file; never included in source context.")
    add.add_argument("--model", help="OpenRouter model for certification, independent of --build-model.")
    add.add_argument("--output", type=Path, help="Certification result path.")
    add.add_argument("--no-view", action="store_true", help="Certify without starting the live viewer.")
    add.add_argument("-y", "--yes", action="store_true", help="Confirm certification without prompting.")
    configure_sdk_parser(add)
    add.set_defaults(agent_handler=_add)


def execute(args: Namespace) -> int:
    handler = getattr(args, "agent_handler", None)
    if not callable(handler):
        raise RuntimeError("No Agent command handler registered")
    try:
        return handler(args)
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"Agent add error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Agent onboarding cancelled; completed files are preserved.", file=sys.stderr)
        return 130


def _add(args: Namespace) -> int:
    if not args.build and (args.with_observe or args.agent_timeout is not None or args.adapter_context):
        raise ValueError("--with-observe, --agent-timeout and --adapter-context require -b")
    print("Preparing Agent source...", file=sys.stderr)
    if args.build or args.certify:
        from agentbench.onboarding.resume import download_or_reuse
        result = download_or_reuse(args.repository, args.agents_dir)
    else:
        result = download_agent(args.repository, args.agents_dir)
    print(f"Agent directory: {result.directory}", file=sys.stderr)
    print(f"Source revision: {result.revision}", file=sys.stderr)
    for warning in result.warnings:
        print(f"Warning: {warning}", file=sys.stderr)
    print("Files relative to agent/ (source downloaded; benchmark configuration pending):",
          file=sys.stderr)
    print(json.dumps(result.files, ensure_ascii=False, indent=2))
    if args.build or args.certify:
        from agentbench.onboarding.workflow import configure_download
        return configure_download(result, args, output_fn=lambda message: print(message, file=sys.stderr))
    return 0


FEATURE = CommandFeature(
    name="agent",
    help="Download and inspect Agent source for onboarding.",
    description="Prepare Agent source using numbered resource folders.",
    configure=configure_parser,
    execute=execute,
)
