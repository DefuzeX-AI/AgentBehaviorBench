"""Shared benchmark execution for CLI command features."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from builtins import print as builtin_print
import sys

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
    print_run_queued,
    print_suite_summary,
    print_viewer_footer,
)
from .terminal_ui.progress import ProgressPrinter, configuration_error
from .terminal_ui.live_cases import LiveCases
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
            try:
                stop_viewer(execution.viewer)
            finally:
                if execution.result_log is not None:
                    from .sessions.control import close_control
                    close_control(execution.result_log.path)
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
    parallelism = runner.concurrency.max_parallel_cases  # Configured concurrent Case limit.
    total_case_count = sum(agent.case_count for agent in agents) # Agent x Case = total Case count
    effective_workers = min(total_case_count, parallelism)
    concurrent = effective_workers > 1

    
    result_log: ResultLogWriter | None = None
    viewer: RunningViewer | None = None
    activity = llm_activity or LLMActivity(output_fn)
    activity.compact = True
    activity.case_counts = {agent.agent_id: agent.case_count for agent in agents}
    progress_printer = None
    live_cases: LiveCases | None = None
    primary_error = None
    keep_viewer_on_error = False  # Whether to keep the viewer open after an error.
    controller = None

    def close_live_cases() -> None:
        if live_cases is not None:
            live_cases.close()
            activity.set_live_cases(None)

    try:
        if output_path is not None:
            # Factories retain the CLI environment snapshot. Without a factory,
            # capture the environment when the result log starts.
            environ = getattr(getattr(runner, "_runner_factory", None), "environ", None)
            from .sessions.configuration import runner_configuration
            from .sessions.fresh import begin_result_log
            saved_configuration = runner_configuration(runner)
            if saved_configuration is not None and all(isinstance(agent, AgentRegistration) for agent in agents):
                result_log = begin_result_log(output_path, suite_id, agents,
                    configuration=saved_configuration, environ=environ)
            else:
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
                    if hasattr(result_log, 'store'):
                        from .sessions.control import register_control
                        import os
                        controller = register_control(result_log.path, os.environ if environ is None else environ)
                    viewer = viewer_starter(result_log.path)
                except OSError as exc:
                    if controller is not None:
                        controller.close()
                        controller = None
                    output_fn(f'Live viewer unavailable: {exc}. Results will still be saved.')
        print_run_queued(len(agents), suite_id, viewer.url if viewer else None,
                         effective_workers, parallelism, output_fn)
        activity.set_concurrent(concurrent)
        if concurrent and output_fn is builtin_print and sys.stdout.isatty():
            live_cases = LiveCases({agent.agent_id: agent.case_count for agent in agents}, effective_workers)
            activity.set_live_cases(live_cases)
        progress_printer = ProgressPrinter(output_fn, llm_activity=activity, concurrent=concurrent,
                                           live_cases=live_cases)

        def terminal_output(line: str) -> None:
            (live_cases.write if live_cases is not None else output_fn)(line)


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
            if live_cases is not None and event.get("event") in {"case_prepared", "case_started", "case_completed"}:
                live_cases.on_event(event)
            elif event.get('event') == 'case_started':
                activity.show_case_status(event.get('agent_id'), event.get('case_index'), 'Running Agent')
            elif event.get('event') == 'case_completed' and not concurrent:
                activity.close()

        def on_tick() -> None:
            if result_log is not None:
                result_log.flush_if_due()
            if live_cases is not None:
                live_cases.flush()

        # step 2: run suite
        def on_agent_complete(item):
            if not concurrent:
                activity.close()
            _handle_agent_complete(item, terminal_output, None if viewer is None else viewer.url,
                                   concurrent=concurrent)

        recovery_options = {}
        if result_log is not None and hasattr(result_log, 'store'):
            recovery_options['retain_case'] = result_log.store.retain_case
        result = runner.run(
            agents,  # Agents under evaluation.
            suite_id=suite_id,
            # Render the start of an Agent run.
            on_agent_start=lambda agent, index, total: print_agent_start(agent, index, total, terminal_output),
            # Render the completion of an Agent run.
            on_agent_complete=on_agent_complete,
            on_progress=progress_printer,
            on_event=on_event,
            on_tick=on_tick if result_log is not None or live_cases is not None else None,
            **recovery_options,
        )

        close_live_cases()
        if result_log is not None:
            result_log.append_suite_complete(result)
        print_suite_summary(result, output_fn)
        if result_log is not None:
            print_viewer_footer(
                result_log.path, None if viewer is None else viewer.url, output_fn
            )
        return BenchmarkExecution(0 if result.passed else 1, result, result_log, viewer)
    except (ProviderSelectionError, SuiteConfigurationError) as exc:
        close_live_cases()
        primary_error, keep_viewer_on_error = exc, True
        _retain_failure(result_log, exc, output_fn)
        _after_failure(lambda: output_fn(configuration_error(exc)), exc, "Display configuration error", output_fn)
        if result_log is not None:
            _after_failure(lambda: print_viewer_footer(
                result_log.path, None if viewer is None else viewer.url, output_fn), exc, "Display result path", output_fn)
        return BenchmarkExecution(1, None, result_log, viewer)
    except KeyboardInterrupt as exc:
        close_live_cases()
        primary_error = exc
        retained = _retain_failure(result_log, exc, output_fn)
        message = ('Benchmark interrupted.' if result_log is None else
                   'Benchmark interrupted; results retained.' if retained
                   else 'Benchmark interrupted; some results could not be saved.')
        _after_failure(lambda: output_fn(message), exc, "Display interruption", output_fn)
        return BenchmarkExecution(130, None, result_log, None)
    except BaseException as exc:
        close_live_cases()
        primary_error = exc
        _retain_failure(result_log, exc, output_fn)
        raise
    finally:
        close_live_cases()
        cleanup_error = None
        actions = [("Close terminal progress", activity.close if progress_printer is None else progress_printer.close)]
        if result_log is not None:
            actions.append(("Flush result log", result_log.flush))
            if hasattr(result_log, 'close'):
                actions.append(('Release Suite writer', result_log.close))
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
        if controller is not None and (viewer is None or cleanup_error is not None
                                      or (primary_error is not None and not keep_viewer_on_error)):
            _after_failure(controller.close, primary_error or cleanup_error, 'Close recovery controller', output_fn)
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
