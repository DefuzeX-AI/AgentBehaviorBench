"""Serve a saved AgentBench result artifact."""

from __future__ import annotations

from argparse import ArgumentParser, ArgumentTypeError, Namespace

from agentbench.cli.viewer import DEFAULT_HOST, DEFAULT_PORT, serve_result_log, ViewerUnavailable

from .base import CommandFeature


def viewer_port(value):
    """Accept TCP ports and zero for an automatically assigned local port."""
    number = int(value)
    if not 0 <= number <= 65535:
        raise ArgumentTypeError('Port must be between 0 and 65535')
    return number


def configure_parser(parser: ArgumentParser) -> None:
    parser.add_argument("result_log", help="Path to an AgentBench JSON result snapshot.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=viewer_port, default=DEFAULT_PORT)


def execute(args: Namespace) -> int:
    try:
        serve_result_log(args.result_log, host=args.host, port=args.port)
    except ViewerUnavailable as exc:
        print(str(exc))
        return 1
    except (OSError, ValueError, OverflowError) as exc:
        print(f'Result viewer error: {exc}')
        return 2
    return 0


FEATURE = CommandFeature(
    name="view",
    help="Open a saved benchmark result in the local viewer.",
    description="Serve a local AgentBench result viewer.",
    configure=configure_parser,
    execute=execute,
)
