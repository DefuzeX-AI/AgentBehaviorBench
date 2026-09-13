"""Run all enabled, ready benchmark agents."""

from __future__ import annotations

import time
from argparse import ArgumentParser, Namespace
from collections.abc import Callable, Mapping
from pathlib import Path

from agentbench.cli.terminal_ui.constants import LOGO_PAUSE_SECONDS
from agentbench.cli.environment import load_project_environment
from agentbench.cli.execution import run_benchmark_session
from agentbench.cli.terminal_ui.logo import print_logo
from agentbench.cli.terminal_ui.presentation import (
    confirm_agents,
    print_agents,
)
from agentbench.cli.sdk import configure_sdk_parser, sdk_arguments
from agentbench.cli.terminal_ui import LLMActivity
from agentbench.cli.trace_runtime import build_trace_suite_runner
from agentbench.cli.viewer import RunningViewer, start_viewer_server
from agentbench.harness import SDK, ProviderSelectionError, SuiteRunner
from agentbench.harness.registry import load_registry
from agentbench.runtime.interception import DEFAULT_TRACE_MAX_BYTES
from agentbench.sdk.plugins import SDKSelection

from .base import CommandFeature

DEFAULT_REGISTRY_PATH = (
    Path(__file__).resolve().parents[3] / "resources" / "registry.toml"
)


def configure_parser(parser: ArgumentParser) -> None:
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH, help="Agent registry path")
    configure_sdk_parser(parser)
    parser.add_argument(
        "--env-file",
        metavar="PATH",
        help="Load host secrets and defaults from PATH instead of .env.",
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        default="results/result.json",
        help=(
            "Write a unique JSON result snapshot, including "
            "trace-like step data (default: results/result.json)."
        ),
    )
    parser.add_argument('--no-view', action='store_true',
                        help='Save results without starting the local live viewer.')
    parser.add_argument('--yes', action='store_true',
                        help='Accept the charge and skip the confirmation prompt.')
    parser.add_argument(
        "--model",
        metavar="OPENROUTER_MODEL",
        help="OpenRouter model slug; defaults to OPENROUTER_MODEL.",
    )
    parser.add_argument(
        "--llm-trace",
        choices=("off", "terminal"),
        default="off",
        help="Print sanitized intercepted model requests and responses.",
    )
    parser.add_argument(
        "--llm-trace-max-bytes",
        type=int,
        default=DEFAULT_TRACE_MAX_BYTES,
        metavar="BYTES",
        help="Legacy option: streaming memory spool threshold; payloads are never truncated.",
    )


def execute(args: Namespace) -> int:
    load_project_environment(args.env_file)
    try:
        kwargs: dict[str, object] = {"output_path": args.output, **sdk_arguments(args)}
        if args.registry != DEFAULT_REGISTRY_PATH:
            kwargs["registry_path"] = args.registry
    except ProviderSelectionError as exc:
        print(f"SDK configuration error: {exc}")
        return 2
    if args.model is not None:
        kwargs["model"] = args.model
    if args.no_view:
        kwargs['viewer_starter'] = None
    if args.yes:
        kwargs['assume_yes'] = True
    if args.llm_trace != "off":
        kwargs["llm_trace"] = args.llm_trace
    if args.llm_trace_max_bytes != DEFAULT_TRACE_MAX_BYTES:
        kwargs["llm_trace_max_bytes"] = args.llm_trace_max_bytes
    return run(**kwargs)


def run(
    registry_path: str | Path = DEFAULT_REGISTRY_PATH,
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
    suite_runner: SuiteRunner | None = None,
    sdk: SDK | None = None,
    sdk_selection: SDKSelection | None = None,
    sdk_options: Mapping[str, object] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    output_path: str | Path | None = None,
    viewer_starter: Callable[[Path], RunningViewer] | None = start_viewer_server,
    post_run_input_fn: Callable[[str], str] = input,
    llm_trace: str = "off",
    llm_trace_max_bytes: int = DEFAULT_TRACE_MAX_BYTES,
    model: str | None = None,
    assume_yes: bool = False,
) -> int:
    """Confirm ready Agents, run the suite, and return a shell exit code."""
    if sdk is not None and sdk_selection is not None:
        raise ValueError("Pass sdk or sdk_selection, not both")
    if suite_runner is not None and (
        sdk is not None or sdk_selection is not None or sdk_options is not None
    ):
        raise ValueError(
            "Configure sdk on the supplied suite_runner, or omit suite_runner"
        )

    print_logo(output_fn)
    sleep_fn(LOGO_PAUSE_SECONDS)

    registry = load_registry(registry_path)
    agents = registry.ready()
    if not agents:
        print_agents(agents, output_fn)
        output_fn("No enabled ready benchmark agents detected.")
        return 1

    adapting = registry.enabled_with_status("adapting")
    if adapting:
        agent_word = "Agent" if len(adapting) == 1 else "Agents"
        output_fn(
            f"{len(adapting)} adapting {agent_word} excluded from this run. "
            "Use 'agentbench certify <agent_id>' when an adapter is ready."
        )

    if not confirm_agents(
        agents,
        input_fn=input_fn,
        output_fn=output_fn,
        sleep_fn=sleep_fn,
        assume_yes=assume_yes,
    ):
        return 0

    llm_activity = LLMActivity(output_fn)
    runner = suite_runner or build_trace_suite_runner(
        mode=llm_trace,
        max_bytes=llm_trace_max_bytes,
        output_fn=output_fn,
        model=model,
        activity_sink=llm_activity,
        sdk=sdk,
        sdk_selection=sdk_selection,
        sdk_options=sdk_options,
    )
    execution = run_benchmark_session(agents, runner=runner, output_path=output_path,
        output_fn=output_fn, viewer_starter=viewer_starter, llm_activity=llm_activity,
        input_fn=post_run_input_fn)
    return execution.exit_code


FEATURE = CommandFeature(
    name="run",
    help="Run all enabled Agents whose status is ready.",
    description="Discover, confirm, and benchmark registered ready Agents.",
    configure=configure_parser,
    execute=execute,
    default=True,
)
