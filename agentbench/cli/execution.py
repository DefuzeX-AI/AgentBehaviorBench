"""Shared benchmark execution for CLI command features."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from agentbench.harness import (
    ProviderSelectionError,
    SuiteAgentResult,
    SuiteConfigurationError,
    SuiteRunner,
)
from agentbench.harness.registry import AgentRegistration
from agentbench.harness.result import BenchmarkSuiteResult

from .terminal_ui.presentation import (
    agent_view_url,
    print_agent_complete,
    print_agent_start,
    print_suite_summary,
    print_viewer_footer,
)
from .terminal_ui.progress import ProgressPrinter, configuration_error
from .result_export import ResultLogWriter, start_result_log
from .terminal_ui import LLMActivity
from .viewer import RunningViewer


def run_benchmark_session(
    agents: tuple[AgentRegistration, ...], *, runner: SuiteRunner,
    output_path: str | Path | None, output_fn: Callable[[str], None],
    viewer_starter: Callable[[Path], RunningViewer] | None,
    llm_activity: LLMActivity | None = None,
    input_fn: Callable[[str], str] = input,
) -> BenchmarkExecution:
    """Own viewer lifetime and fresh-suite reruns for every evaluation command."""
    from .terminal_ui.presentation import request_viewer_action, panel_rule, panel_line
    from .terminal_ui.constants import ANSI_GREEN
    while True:
        execution = run_benchmark_once(agents, runner=runner, output_path=output_path,
            output_fn=output_fn, viewer_starter=viewer_starter, llm_activity=llm_activity)
        if execution.viewer is None:
            return execution
        try:
            if execution.result_log is None:
                return execution
            action = request_viewer_action(execution.result_log.path, execution.viewer.url,
                                           input_fn=input_fn, output_fn=output_fn)
        finally:
            stop_viewer(execution.viewer)
        if action != 'rerun':
            return execution
        output_fn('')
        output_fn(panel_rule('RERUN QUEUED', ANSI_GREEN))
        output_fn(panel_line('Starting a fresh benchmark run'))
        output_fn(panel_rule('', ANSI_GREEN))

ViewerStarter = Callable[[Path], RunningViewer]


@dataclass(frozen=True)
class BenchmarkExecution:
    exit_code: int
    result: BenchmarkSuiteResult | None
    result_log: ResultLogWriter | None
    viewer: RunningViewer | None


def run_benchmark_once(
    agents: tuple[AgentRegistration, ...],
    *,
    runner: SuiteRunner,
    output_path: str | Path | None,
    output_fn: Callable[[str], None],
    viewer_starter: ViewerStarter | None,
    llm_activity: LLMActivity | None = None,
) -> BenchmarkExecution:
    suite_id = runner.new_suite_id()
    result_log: ResultLogWriter | None = None
    viewer: RunningViewer | None = None
    if output_path is not None:
        result_log = start_result_log(
            output_path,
            suite_id=suite_id,
            selected_agent_ids=tuple(agent.agent_id for agent in agents),
        )
        if viewer_starter is not None:
            try:
                viewer = viewer_starter(result_log.path)
            except OSError as exc:
                output_fn(f'Live viewer unavailable: {exc}. Results will still be saved.')
        output_fn(f"Suite ID: {suite_id}")
        output_fn(f"Result artifact started: {result_log.path}")
        if viewer is not None:
            output_fn(f"View: {viewer.url}")

    activity = llm_activity or LLMActivity(output_fn)
    progress_printer = ProgressPrinter(output_fn, llm_activity=activity)
    def on_progress(event):
        if result_log is not None:
            result_log.append_progress(event)
        progress_printer(event)
    try:
        try:
            result = runner.run(
                agents,
                suite_id=suite_id,
                on_agent_start=lambda agent, index, total: print_agent_start(
                    agent, index, total, output_fn
                ),
                on_agent_complete=lambda item: _handle_agent_complete(
                    item,
                    output_fn,
                    result_log,
                    None if viewer is None else viewer.url,
                ),
                on_progress=on_progress,
                on_step_start=(
                    None if result_log is None else result_log.append_step_started
                ),
                on_step_complete=(
                    None if result_log is None else result_log.append_step_completed
                ),
                on_step_failure=(
                    None if result_log is None else result_log.append_step_failed
                ),
            )
        except (ProviderSelectionError, SuiteConfigurationError) as exc:
            if result_log is not None:
                result_log.append_suite_error(exc)
            output_fn(configuration_error(exc))
            if result_log is not None:
                print_viewer_footer(
                    result_log.path, None if viewer is None else viewer.url, output_fn
                )
            return BenchmarkExecution(1, None, result_log, viewer)
    except KeyboardInterrupt:
        if viewer is not None:
            stop_viewer(viewer)
        if result_log is not None:
            result_log.append_suite_error(RuntimeError('Benchmark interrupted'))
        output_fn('Benchmark interrupted; results retained.')
        return BenchmarkExecution(130, None, result_log, None)
    except BaseException as exc:
        if viewer is not None:
            stop_viewer(viewer)
        if result_log is not None:
            result_log.append_suite_error(RuntimeError(str(exc)))
        raise
    finally:
        progress_printer.close()

    try:
        if result_log is not None:
            result_log.append_suite_complete(result)
        print_suite_summary(result, output_fn)
        if result_log is not None:
            print_viewer_footer(
                result_log.path, None if viewer is None else viewer.url, output_fn
            )
    except BaseException:
        if viewer is not None:
            stop_viewer(viewer)
        raise
    return BenchmarkExecution(0 if result.passed else 1, result, result_log, viewer)


def stop_viewer(viewer: RunningViewer) -> None:
    stop = getattr(viewer, "stop", None)
    if callable(stop):
        stop()


def _handle_agent_complete(
    item: SuiteAgentResult,
    output_fn: Callable[[str], None],
    result_log: ResultLogWriter | None,
    viewer_url: str | None,
) -> None:
    print_agent_complete(item, output_fn)
    if result_log is not None:
        result_log.append_agent_complete(item)
    if viewer_url is not None:
        output_fn(f"View: {agent_view_url(viewer_url, item.agent_id)}")
