"""Certify one adapting Agent and promote it to ready."""

from __future__ import annotations

import re
from argparse import ArgumentParser, Namespace
from collections.abc import Callable, Mapping
from pathlib import Path

from agentbench.cli.environment import load_project_environment
from agentbench.cli.execution import run_benchmark_session
from agentbench.cli.viewer import start_viewer_server
from agentbench.cli.registry_status import RegistryStatusError, update_agent_status
from agentbench.cli.sdk import configure_sdk_parser, sdk_arguments
from agentbench.cli.terminal_ui import LLMActivity
from agentbench.cli.terminal_ui.presentation import confirm_agents
from agentbench.cli.trace_runtime import build_trace_suite_runner
from agentbench.harness import (
    SDK,
    BenchmarkSuiteResult,
    ProviderSelectionError,
    SuiteRunner,
)
from agentbench.harness.registry import load_registry
from agentbench.runtime.interception import DEFAULT_TRACE_MAX_BYTES
from agentbench.sdk.plugins import SDKSelection

from .base import CommandFeature
from .run import DEFAULT_REGISTRY_PATH


def configure_parser(parser: ArgumentParser) -> None:
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH, help="Agent registry path")
    configure_sdk_parser(parser)
    parser.add_argument('--no-view', action='store_true', help='Save results without starting the live viewer.')
    parser.add_argument('--yes', action='store_true', help='Accept the charge and skip the confirmation prompt.')
    parser.add_argument("agent_id", help="Registered adapting Agent to certify.")
    parser.add_argument(
        "--env-file",
        metavar="PATH",
        help="Load host secrets and defaults from PATH instead of .env.",
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        help="Optional base path for the JSON certification snapshot.",
    )
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
    return certify(args.agent_id, **kwargs)


def certify(
    agent_id: str,
    *,
    registry_path: str | Path = DEFAULT_REGISTRY_PATH,
    output_path: str | Path | None = None,
    output_fn: Callable[[str], None] = print,
    suite_runner: SuiteRunner | None = None,
    sdk: SDK | None = None,
    sdk_selection: SDKSelection | None = None,
    sdk_options: Mapping[str, object] | None = None,
    llm_trace: str = "off",
    llm_trace_max_bytes: int = DEFAULT_TRACE_MAX_BYTES,
    model: str | None = None,
    viewer_starter=start_viewer_server,
    post_run_input_fn=input,
    input_fn: Callable[[str], str] = input,
    assume_yes: bool = False,
) -> int:
    """Run one adapting Agent and promote it after adapter execution succeeds."""
    if sdk is not None and sdk_selection is not None:
        raise ValueError("Pass sdk or sdk_selection, not both")
    if suite_runner is not None and (
        sdk is not None or sdk_selection is not None or sdk_options is not None
    ):
        raise ValueError(
            "Configure sdk on the supplied suite_runner, or omit suite_runner"
        )

    registry = load_registry(registry_path)
    try:
        agent = registry.find(agent_id)
    except (KeyError, ValueError) as exc:
        output_fn(f"Certification error: {exc}")
        return 2

    if agent.status == "ready":
        output_fn(f"Agent '{agent_id}' is already ready.")
        return 0
    if agent.status != "adapting":
        output_fn(
            f"Certification error: Agent '{agent_id}' has status "
            f"'{agent.status}', expected 'adapting'."
        )
        return 2

    artifact_base = output_path or _default_output_path(registry_path, agent_id)
    output_fn(f"Certifying adapting Agent: {agent_id}")
    output_fn(
        "The registry will change to ready if the Agent completes its Cases "
        "without invocation errors."
    )
    # Certification runs the full benchmark flow and rewrites the registry, so it
    # asks before spending, exactly as run does.
    if not confirm_agents((agent,), input_fn=input_fn, output_fn=output_fn,
                          assume_yes=assume_yes):
        return 0
    llm_activity = LLMActivity(output_fn)
    execution = run_benchmark_session(
        (agent,),
        runner=suite_runner
        or build_trace_suite_runner(
            mode=llm_trace,
            max_bytes=llm_trace_max_bytes,
            output_fn=output_fn,
            model=model,
            activity_sink=llm_activity,
            sdk=sdk,
            sdk_selection=sdk_selection,
            sdk_options=sdk_options,
        ),
        output_path=artifact_base,
        output_fn=output_fn,
        viewer_starter=viewer_starter,
        input_fn=post_run_input_fn,
        llm_activity=llm_activity,
    )
    if execution.result is None or not _agent_completed_certification(
        execution.result, agent_id
    ):
        output_fn(f"Certification failed. Agent '{agent_id}' remains adapting.")
        return execution.exit_code

    try:
        update_agent_status(
            registry_path,
            agent_id,
            expected_status="adapting",
            new_status="ready",
        )
    except RegistryStatusError as exc:
        output_fn(f"Certification passed, but registry update failed: {exc}")
        return 2

    if execution.result.passed:
        output_fn(f"Certification passed. Agent '{agent_id}' is now ready.")
    else:
        output_fn(
            f"Certification completed with benchmark failures. Agent '{agent_id}' is now ready."
        )
    return 0


def _agent_completed_certification(result: BenchmarkSuiteResult, agent_id: str) -> bool:
    if result.skipped_count != 0:
        return False
    if len(result.items) != 1:
        return False
    item = result.items[0]
    return (
        item.agent_id == agent_id
        and item.error_type is None
        and item.completed_case_count == item.requested_case_count
    )


def _default_output_path(registry_path: str | Path, agent_id: str, *, command="certify") -> Path:
    repo_root = Path(registry_path).resolve().parent.parent
    safe_agent_id = re.sub(r"[^A-Za-z0-9._-]+", "-", agent_id).strip("-")
    return repo_root / "results" / f"{command}-{safe_agent_id or 'agent'}.json"


FEATURE = CommandFeature(
    name="certify",
    help="Run one adapting Agent and promote it to ready after execution succeeds.",
    description=(
        "Execute the full benchmark flow for one adapting Agent and update "
        "its registry status after it completes all requested Cases without "
        "invocation errors."
    ),
    configure=configure_parser,
    execute=execute,
)
