"""Serve a saved AgentBench result artifact."""

from __future__ import annotations

from argparse import ArgumentParser, Namespace

from agentbench.cli.viewer import DEFAULT_HOST, DEFAULT_PORT, serve_result_log, ViewerUnavailable

from .base import CommandFeature


def configure_parser(parser: ArgumentParser) -> None:
    parser.add_argument("result_log", help="Path to an AgentBench JSON result snapshot.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)


def execute(args: Namespace) -> int:
    try:
        serve_result_log(args.result_log, host=args.host, port=args.port)
    except ViewerUnavailable as exc:
        print(str(exc))
        return 1
    return 0


FEATURE = CommandFeature(
    name="view",
    help="Open a saved benchmark result in the local viewer.",
    description="Serve a local AgentBench result viewer.",
    configure=configure_parser,
    execute=execute,
)
