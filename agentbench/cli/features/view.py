"""Serve a saved AgentBench result artifact."""

from __future__ import annotations

from argparse import ArgumentParser, ArgumentTypeError, Namespace

from agentbench.cli.viewer import DEFAULT_HOST, DEFAULT_PORT, serve_result_log

from .base import CommandFeature


def port_number(value: str) -> int:
    """Reject a port the socket layer would only refuse at bind time."""
    port = int(value)
    if not 0 <= port <= 65535:
        raise ArgumentTypeError("port must be between 0 and 65535")
    return port


def configure_parser(parser: ArgumentParser) -> None:
    parser.add_argument("result_log", help="Path to an AgentBench JSON result snapshot.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=port_number, default=DEFAULT_PORT)


def execute(args: Namespace) -> int:
    try:
        serve_result_log(args.result_log, host=args.host, port=args.port)
    except (OSError, ValueError) as exc:
        # ViewerUnavailable is an OSError; so are a missing file and a directory.
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
