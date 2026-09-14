"""Run all enabled, ready benchmark agents."""

from __future__ import annotations

import time
from argparse import ArgumentParser, Namespace
from pathlib import Path

from agentbench.cli.configuration import RunConfiguration
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
from agentbench.harness import ProviderSelectionError
from agentbench.harness.registry import load_registry
from agentbench.runtime.interception import DEFAULT_TRACE_MAX_BYTES
from .base import CommandFeature

DEFAULT_REGISTRY_PATH = (
    Path(__file__).resolve().parents[3] / "resources" / "registry.toml"
)


def configure_parser(parser: ArgumentParser) -> None:
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
    parser.add_argument(
        "--model",
        metavar="OPENROUTER_MODEL",
        help="OpenRouter model slug; defaults to OPENROUTER_MODEL.",
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
    except ProviderSelectionError as exc:
        print(f"SDK configuration error: {exc}")
        return 2
    if args.model is not None:
        kwargs["model"] = args.model
    if args.no_view:
        kwargs['viewer_starter'] = None
    if args.llm_trace_max_bytes != DEFAULT_TRACE_MAX_BYTES:
        kwargs["llm_trace_max_bytes"] = args.llm_trace_max_bytes
    return run(RunConfiguration(**kwargs))


def run(configuration: RunConfiguration | None = None) -> int:
    """Confirm ready Agents, run the suite, and return a shell exit code."""

    config = configuration or RunConfiguration()
    if config.sdk is not None and config.sdk_selection is not None:
        raise ValueError("Pass sdk or sdk_selection, not both")

    
    if config.suite_runner is not None and (
        config.sdk is not None
        or config.sdk_selection is not None
        or config.sdk_options is not None
    ):
        raise ValueError(
            "Configure sdk on the supplied suite_runner, or omit suite_runner"
        )

    print_logo(config.output_fn)
    # wait 2 sec
    time.sleep(LOGO_PAUSE_SECONDS)


    # regist agents
    registry = load_registry(DEFAULT_REGISTRY_PATH)
    print(registry)

    # we only pick ready agent, for adpating agent, run verify command first
    agents = registry.ready()
    if not agents:
        print_agents(agents, config.output_fn)
        config.output_fn("No enabled ready benchmark agents detected.")
        return 1

    # display adapting agent, but not run
    adapting = registry.enabled_with_status("adapting")
    if adapting:
        agent_word = "Agent" if len(adapting) == 1 else "Agents"
        config.output_fn(
            f"{len(adapting)} adapting {agent_word} excluded from this run. "
            "Use 'agentbench certify <agent_id>' when an adapter is ready."
        )

    if not confirm_agents(
        agents,
        input_fn=config.input_fn,
        output_fn=config.output_fn,
    ):
        return 0

    # starting bench

    # output LLM data
    llm_activity = LLMActivity(config.output_fn)

    # build benchmark_runner
    suite_runner = config.suite_runner or build_trace_suite_runner(
        max_bytes=config.llm_trace_max_bytes,
        model=config.model,
        activity_sink=llm_activity,
        sdk=config.sdk,
        sdk_selection=config.sdk_selection,
        sdk_options=config.sdk_options,
    )

    execution = run_benchmark_session(
        agents,
        runner=suite_runner,

        output_path=config.output_path,
        input_fn=config.post_run_input_fn,
        output_fn=config.output_fn,

        viewer_starter=config.viewer_starter,
        llm_activity=llm_activity,

    )
    return execution.exit_code


FEATURE = CommandFeature(
    name="run",
    help="Run all enabled Agents whose status is ready.",
    description="Discover, confirm, and benchmark registered ready Agents.",
    configure=configure_parser,
    execute=execute,
    default=True,
)
