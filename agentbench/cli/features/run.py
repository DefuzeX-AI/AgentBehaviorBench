"""Run all enabled, ready benchmark agents."""

from __future__ import annotations

import time
from argparse import ArgumentParser, Namespace
from pathlib import Path

from agentbench.cli.configuration import RunConfiguration
from agentbench.cli.terminal_ui.constants import LOGO_PAUSE_SECONDS
from agentbench.cli.environment import load_project_environment, execution_environment_snapshot
from agentbench.cli.execution import run_benchmark_session
from agentbench.cli.terminal_ui.logo import print_logo
from agentbench.cli.terminal_ui.loading import loading_line
from agentbench.cli.terminal_ui.presentation import (
    confirm_agents,
    print_agents,
)
from agentbench.cli.sdk import configure_sdk_parser
from agentbench.cli.retry_options import configure_retry_parser
from agentbench.cli.benchmark_command import (
    benchmark_arguments,
    benchmark_runner,
    check_execution_arguments,
    configure_benchmark_parser,
    results_directory,
)
from agentbench.cli.terminal_ui import LLMActivity
from agentbench.evaluation.runner import build_trace_suite_runner
from agentbench.harness import ProviderSelectionError
from agentbench.harness.registry import load_registry
from agentbench.project import project_root
from .base import CommandFeature

# A checkout keeps its bundled registry; an installed CLI uses the project it runs in.
DEFAULT_REGISTRY_PATH = project_root() / "resources" / "registry.toml"


def configure_parser(parser: ArgumentParser) -> None:
    configure_sdk_parser(parser)
    configure_retry_parser(parser)
    parser.add_argument('--agent', action='append', default=[], metavar='ID',
                        help='Run only this enabled ready Agent; repeat to select several.')
    parser.add_argument('-y', '--yes', action='store_true', help='Confirm this execution without prompting.')
    configure_benchmark_parser(parser, viewer_help='Save results without starting the local live viewer.')


def execute(args: Namespace) -> int:
    try:
        directory = results_directory(args, lambda: Path('results').resolve())
        load_project_environment(args.env_file)
        loaded = execution_environment_snapshot()
        kwargs = benchmark_arguments(args, loaded, directory)
        if getattr(args, 'agent', None):
            kwargs['agent_ids'] = tuple(args.agent)
    except (ProviderSelectionError, ValueError) as exc:
        print(f"SDK configuration error: {exc}")
        return 2
    try:
        return run(RunConfiguration(**kwargs))
    except (OSError, ProviderSelectionError, ValueError, KeyError) as exc:
        print(f'Configuration error: {exc}')
        return 2


def run(configuration: RunConfiguration | None = None) -> int:
    """Confirm ready Agents, run the suite, and return a shell exit code."""

    config = configuration or RunConfiguration()
    check_execution_arguments(
        output_path=config.output_path, results_dir=config.results_dir,
        suite_runner=config.suite_runner, sdk=config.sdk, sdk_selection=config.sdk_selection,
        sdk_options=config.sdk_options, concurrency=config.concurrency, environ=config.environ,
    )

    print_logo(config.output_fn)
    with loading_line("Loading agents", config.output_fn):
        time.sleep(LOGO_PAUSE_SECONDS)
        registry = load_registry(DEFAULT_REGISTRY_PATH)
        agents = registry.ready()
        if config.agent_ids:
            selected = set(config.agent_ids)
            unavailable = selected - {agent.agent_id for agent in agents}
            if unavailable:
                raise ValueError('Selected Agents are not enabled and ready: ' + ', '.join(sorted(unavailable)))
            agents = tuple(agent for agent in agents if agent.agent_id in selected)
        from agentbench.sdk.strategy_checks import check_agents

        checks = None if not agents or config.suite_runner is not None else check_agents(
            agents, selection=config.sdk_selection, sdk=config.sdk, environ=config.environ)

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

    if config.assume_yes:
        print_agents(agents, config.output_fn, strategy_checks=checks)
    if not config.assume_yes and not confirm_agents(
        agents,
        input_fn=config.input_fn,
        output_fn=config.output_fn,
        strategy_checks=checks,
    ):
        return 0

    with loading_line("Preparing benchmark", config.output_fn):
        llm_activity = LLMActivity(config.output_fn)
        suite_runner = benchmark_runner(
            build_trace_suite_runner, suite_runner=config.suite_runner,
            retry_policy=config.retry_policy, llm_trace_max_bytes=config.llm_trace_max_bytes,
            model=config.model, activity=llm_activity, sdk=config.sdk,
            sdk_selection=config.sdk_selection, sdk_options=config.sdk_options,
            concurrency=config.concurrency, environ=config.environ,
        )

    def match_ground_truth(directory):
        from agentbench.evaluation import EvaluationService
        EvaluationService(DEFAULT_REGISTRY_PATH.parent.parent,
                          environ=config.environ).evaluate_gt(directory, output=config.output_fn)

    execution = run_benchmark_session(
        agents,
        runner=suite_runner,

        output_path=config.output_path,
        input_fn=config.post_run_input_fn,
        output_fn=config.output_fn,

        viewer_starter=config.viewer_starter,
        llm_activity=llm_activity,
        after_suite=match_ground_truth,
        **({'results_dir': config.results_dir} if config.results_dir is not None else {}),

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
