"""AgentBench CLI command router."""

from __future__ import annotations

import sys
from argparse import ArgumentParser, Namespace
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from agentbench.harness import SDK, SuiteRunner

from .configuration import RunConfiguration
from .features import FEATURES
from .features.run import run
from .terminal_ui.presentation import confirm_agents
from .viewer import RunningViewer, start_viewer_server


def build_parser() -> ArgumentParser:
    """Build the root parser from independently registered command features."""

    parser = ArgumentParser(
        prog="agentbench",
        description="Run, certify, and inspect registered benchmark Agents.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    # Let each feature add its own command and arguments.
    for feature in FEATURES:
        feature.register(subparsers)
    return parser


def cli(argv: Sequence[str] | None = None) -> int:
    """Parse command-line arguments and dispatch a registered feature."""
    
    args_list = list(sys.argv[1:] if argv is None else argv)
    
    args = build_parser().parse_args(_normalize_argv(args_list))
    handler = _command_handler(args)
    return handler(args)


def main(
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
    suite_runner: SuiteRunner | None = None,
    sdk: SDK | None = None,
    sdk_options: Mapping[str, object] | None = None,
    output_path: str | Path | None = None,
    viewer_starter: Callable[[Path], RunningViewer] = start_viewer_server,
    post_run_input_fn: Callable[[str], str] = input,
) -> int:
    """Run the default benchmark feature through the legacy Python API.

    Args:
        input_fn: Function used to collect the initial confirmation.
        output_fn: Function used to write terminal output.
        suite_runner: Optional runner to use instead of constructing one.

        sdk: Optional SDK instance for the benchmark session.
        sdk_options: Options used when constructing an SDK.

        output_path: Optional destination for result artifacts.
        viewer_starter: Function that starts the local results viewer.
        post_run_input_fn: Function used for prompts after the run completes.
    """

    # sdk and sdk option is python only, cli will accept output and input path
    if (
        sdk is None
        and sdk_options is None
        and _is_stale_console_entry(
            output_path=output_path,
            input_fn=input_fn,
            output_fn=output_fn,
            suite_runner=suite_runner,
        )
    ):
        return cli(sys.argv[1:])

    return run(
        RunConfiguration(
            input_fn=input_fn,
            output_fn=output_fn,
            suite_runner=suite_runner,
            sdk=sdk,
            sdk_options=sdk_options,
            output_path=output_path,
            viewer_starter=viewer_starter,
            post_run_input_fn=post_run_input_fn,
        )
    )


def _normalize_argv(args: list[str]) -> list[str]:
    if not args:
        return [_default_feature_name()]
    if args[0].startswith("-") and args[0] not in {"-h", "--help"}:
        return [_default_feature_name(), *args]
    return args


def _default_feature_name() -> str:
    defaults = [feature.name for feature in FEATURES if feature.default]
    if len(defaults) != 1:
        raise RuntimeError("AgentBench must register exactly one default command")
    return defaults[0]


def _command_handler(args: Namespace) -> Callable[[Namespace], int]:
    handler = getattr(args, "command_handler", None)
    if not callable(handler):
        raise RuntimeError(f"No handler registered for command: {args.command}")
    return handler


def _is_stale_console_entry(
    *,
    output_path: str | Path | None,
    input_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
    suite_runner: SuiteRunner | None,
) -> bool:
    args = sys.argv[1:]
    command_names = {feature.name for feature in FEATURES}
    return (
        output_path is None
        and input_fn is input
        and output_fn is print
        and suite_runner is None
        and bool(args)
        and (args[0] in command_names or args[0].startswith("-"))
    )


__all__ = ["RunConfiguration", "build_parser", "cli", "confirm_agents", "main"]
