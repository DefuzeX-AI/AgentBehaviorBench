"""Shared benchmark execution for CLI command features."""

from __future__ import annotations

from collections.abc import Callable, Mapping
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
    """

        Own viewer lifetime and fresh-suite reruns for every evaluation command.

    """
    from .terminal_ui.presentation import request_viewer_action, panel_rule, panel_line
    from .terminal_ui.constants import ANSI_GREEN
    while True:

        # Run a single benchmark session and return the result if no rerun is requested.
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

    # step 1: prepare suite
    suite_id = runner.new_suite_id()
    parallelism = runner.concurrency.max_parallel_cases # 配置允许同时执行多少个 Case
    total_case_count = sum(agent.case_count for agent in agents) # Agent x Case = total Case count
    effective_workers = min(total_case_count, parallelism)
    concurrent = effective_workers > 1

    
    result_log: ResultLogWriter | None = None
    viewer: RunningViewer | None = None
    activity = llm_activity or LLMActivity(output_fn)
    progress_printer = None
    primary_error = None
    keep_viewer_on_error = False #出错后是否保留viewer

    try:
        if output_path is not None:
            # Factories retain the CLI environment snapshot. Without a factory,
            # capture the environment when the result log starts.
            environ = getattr(getattr(runner, "_runner_factory", None), "environ", None)
            result_log = start_result_log(
                output_path,
                suite_id=suite_id,
                selected_agent_ids=tuple(agent.agent_id for agent in agents),
                configured_workers=parallelism,
                effective_workers=effective_workers,
                total_case_count=total_case_count,
                selected_case_counts={agent.agent_id: agent.case_count for agent in agents},
                batch_progress=concurrent,
                environ=environ if isinstance(environ, Mapping) else None,
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


        output_fn(f"Case workers: {effective_workers} (configured: {parallelism})")
        activity.set_concurrent(concurrent)
        progress_printer = ProgressPrinter(output_fn, llm_activity=activity, concurrent=concurrent)


        def on_event(event):
            '''
            event = {
                "event": "case_started",
                "agent_id": "agent-a",
                "case_index": 0,
                "job_id": "job-123",
                "status": "running",
            }
            '''

            if result_log is not None:
                result_log.append_event(event)
            if event.get("event") in {"case_started", "case_completed"}:
                case_index = event.get("case_index")
                label = case_index + 1 if isinstance(case_index, int) else "?"
                output_fn(f"[{event.get('agent_id')} | case={label} | job={event.get('job_id')}] "
                          f"{event['event']}: {event.get('status', 'running')}")

        # step 2: run suite
        result = runner.run(
            agents, # 被测的agents
            suite_id=suite_id,
            # 某个 Agent 开始时，怎么显示
            on_agent_start=lambda agent, index, total: print_agent_start(agent, index, total, output_fn),
            # 某个 Agent 完成时，怎么显示
            on_agent_complete=lambda item: _handle_agent_complete(
                item, output_fn, None if viewer is None else viewer.url, concurrent=concurrent),
            on_progress=progress_printer,
            on_event=on_event,
            on_tick=None if result_log is None else result_log.flush_if_due,
        )

        if result_log is not None:
            result_log.append_suite_complete(result)
        print_suite_summary(result, output_fn)
        if result_log is not None:
            print_viewer_footer(
                result_log.path, None if viewer is None else viewer.url, output_fn
            )
        return BenchmarkExecution(0 if result.passed else 1, result, result_log, viewer)
    except (ProviderSelectionError, SuiteConfigurationError) as exc:
        primary_error, keep_viewer_on_error = exc, True
        _retain_failure(result_log, exc, output_fn)
        _after_failure(lambda: output_fn(configuration_error(exc)), exc, "Display configuration error", output_fn)
        if result_log is not None:
            _after_failure(lambda: print_viewer_footer(
                result_log.path, None if viewer is None else viewer.url, output_fn), exc, "Display result path", output_fn)
        return BenchmarkExecution(1, None, result_log, viewer)
    except KeyboardInterrupt as exc:
        primary_error = exc
        retained = _retain_failure(result_log, exc, output_fn)
        message = ('Benchmark interrupted.' if result_log is None else
                   'Benchmark interrupted; results retained.' if retained
                   else 'Benchmark interrupted; some results could not be saved.')
        _after_failure(lambda: output_fn(message), exc, "Display interruption", output_fn)
        return BenchmarkExecution(130, None, result_log, None)
    except BaseException as exc:
        primary_error = exc
        _retain_failure(result_log, exc, output_fn)
        raise
    finally:
        cleanup_error = None
        actions = [("Close terminal progress", activity.close if progress_printer is None else progress_printer.close)]
        if result_log is not None:
            actions.append(("Flush result log", result_log.flush))
        for label, action in actions:
            if primary_error is not None or cleanup_error is not None:
                _after_failure(action, primary_error or cleanup_error, label, output_fn)
            else:
                try:
                    action()
                except BaseException as exc:
                    cleanup_error = exc
        if viewer is not None and (cleanup_error is not None or (primary_error is not None and not keep_viewer_on_error)):
            _after_failure(lambda: stop_viewer(viewer), primary_error or cleanup_error, "Stop viewer", output_fn)
        if cleanup_error is not None:
            raise cleanup_error


def _after_failure(action, primary, label, output_fn) -> bool:
    """Attempt independent cleanup without replacing the actual run failure."""
    try:
        action()
        return True
    except BaseException as secondary:
        message = f"{label} failed: {type(secondary).__name__}: {secondary}"
        add_note = getattr(primary, "add_note", None)
        if callable(add_note):
            add_note(message)
        try:
            output_fn(message)
        except BaseException:
            pass  # A broken terminal must not discard the original exception.
        return False


def _retain_failure(result_log, exc, output_fn) -> bool:
    if result_log is None:
        return False
    partial = getattr(exc, "partial_items", ())
    saved = _after_failure(lambda: result_log.append_partial_results(partial), exc, "Save partial results", output_fn)
    error = RuntimeError("Benchmark interrupted") if isinstance(exc, KeyboardInterrupt) else exc
    return _after_failure(lambda: result_log.append_suite_error(error), exc, "Save suite error", output_fn) and saved


def stop_viewer(viewer: RunningViewer) -> None:
    stop = getattr(viewer, "stop", None)
    if callable(stop):
        stop()


def _handle_agent_complete(
    item: SuiteAgentResult,
    output_fn: Callable[[str], None],
    viewer_url: str | None,
    *,
    concurrent: bool = False,
) -> None:
    print_agent_complete(item, (lambda text: output_fn(f"[{item.agent_id}] {text}"))
                         if concurrent else output_fn)
    if viewer_url is not None:
        output_fn(f"View: {agent_view_url(viewer_url, item.agent_id)}")
