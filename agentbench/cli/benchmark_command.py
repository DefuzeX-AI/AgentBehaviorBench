"""Options and checks shared by `run` and `certify`, the registry benchmark commands.

Each command still calls its own environment loader, registry, confirmation and
runner factory; this module only parses, validates and assembles arguments.
"""

from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Callable
from pathlib import Path

from agentbench.cli.options import configure_env_file, configure_model
from agentbench.cli.result.paths import configure_result_paths, legacy_result_notice, validate_results_dir
from agentbench.cli.retry_options import retry_policy_argument
from agentbench.cli.sdk import sdk_arguments
from agentbench.runtime.interception import DEFAULT_TRACE_MAX_BYTES


def configure_benchmark_parser(parser: ArgumentParser, *, viewer_help: str) -> None:
    configure_env_file(parser)
    configure_result_paths(parser, legacy_option='--output')
    parser.add_argument('--no-view', action='store_true', help=viewer_help)
    configure_model(parser)
    parser.add_argument(
        "--llm-trace-max-bytes",
        type=int,
        default=DEFAULT_TRACE_MAX_BYTES,
        metavar="BYTES",
        help="Legacy option: streaming memory spool threshold; payloads are never truncated.",
    )


def results_directory(args: Namespace, default: Callable[[], Path]) -> Path | None:
    """Resolve the ABB result directory, using `default` when no location is given."""
    directory = validate_results_dir(args.output, getattr(args, 'results_dir', None))
    if args.output is None and directory is None:
        directory = default()
    if args.output is not None:
        legacy_result_notice('--output', args.output, print)
    return directory


def benchmark_arguments(args: Namespace, loaded, directory: Path | None) -> dict[str, object]:
    """Keyword arguments common to run() and certify(); explicit options only."""
    kwargs: dict[str, object] = {"output_path": args.output, "assume_yes": args.yes,
                                 "concurrency": loaded.concurrency, "environ": loaded.environ,
                                 **sdk_arguments(args)}
    if directory is not None:
        kwargs['results_dir'] = directory
    policy = retry_policy_argument(args)
    if policy is not None:
        kwargs['retry_policy'] = policy
    if args.model is not None:
        kwargs["model"] = args.model
    if args.no_view:
        kwargs['viewer_starter'] = None
    if args.llm_trace_max_bytes != DEFAULT_TRACE_MAX_BYTES:
        kwargs["llm_trace_max_bytes"] = args.llm_trace_max_bytes
    return kwargs


def check_execution_arguments(*, output_path, results_dir, suite_runner, sdk, sdk_selection,
                              sdk_options, concurrency, environ) -> None:
    validate_results_dir(output_path, results_dir)
    if sdk is not None and sdk_selection is not None:
        raise ValueError("Pass sdk or sdk_selection, not both")
    if suite_runner is not None and (
        sdk is not None or sdk_selection is not None or sdk_options is not None
        or concurrency is not None or environ is not None
    ):
        raise ValueError(
            "Configure sdk on the supplied suite_runner, or omit suite_runner"
        )


def benchmark_runner(factory, *, suite_runner, retry_policy, llm_trace_max_bytes, model, activity,
                     sdk, sdk_selection, sdk_options, concurrency, environ):
    """Use the supplied runner or build one with the caller's factory."""
    runner = suite_runner or factory(
        max_bytes=llm_trace_max_bytes,
        model=model,
        activity_sink=activity,
        sdk=sdk,
        sdk_selection=sdk_selection,
        sdk_options=sdk_options,
        concurrency=concurrency,
        environ=environ,
    )
    if retry_policy is not None:
        runner.retry_policy = retry_policy
    return runner
