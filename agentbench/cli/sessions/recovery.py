"""One recovery entry shared by terminal commands and the local Viewer."""

from agentbench.harness.result import BenchmarkSuiteResult
from agentbench.harness.scheduling.resume import resume_seeds
from agentbench.harness.session import SuiteStore
from agentbench.harness.session.references import history_guard, register_suite_reference
from agentbench.cli.history import PROJECT_ROOT

from .configuration import build_saved_runner, runner_configuration
from .log import SuiteResultLog


def execute_recovery(directory, *, environ, selection=None, replay=False, command_id=None,
                     runner=None, on_event=None, on_runner=None, run_control=None):
    """Resume a locked saved Suite and retain every original Case outcome.

    Args:
        directory: Canonical directory containing plan.json and events.json.
        environ: Credential/default snapshot, never persisted in the Suite plan.
        selection: Optional (Agent ID, zero-based Case index) positions.
        replay: Explicitly rerun selected failed Cases from their first Input.
        command_id: Optional idempotent command identity from the Viewer.
        runner: Optional injected runner for public integration tests.
        on_event: Optional coordinator event observer.
        on_runner: Callback receiving the active runner for cancellation.
        run_control: Optional command-owned cancellation signal, valid before the
            runner initializes and passed unchanged into Suite execution.
    Returns:
        BenchmarkSuiteResult. Failed or blocked Cases remain in this result.
    Raises:
        SuiteLockedError if another coordinator owns this Suite; provenance,
        artifact, SDK, or execution errors are retained and propagated.
    """
    if run_control is not None:
        run_control.check()
    with SuiteStore.open(directory, environ=environ) as store:
        with history_guard(PROJECT_ROOT):
            register_suite_reference(store.directory, project_root=PROJECT_ROOT)
        runner = runner or build_saved_runner(store.plan['configuration'], environ)
        current = runner_configuration(runner)
        store.validate_provenance(configuration=current if current is not None else store.plan['configuration'])
        if command_id:
            previous = [event for event in store.events if event.get('command_id') == command_id]
            if previous and previous[-1].get('status') == 'completed':
                raise ValueError('This recovery command has already completed')
        seeds = resume_seeds(store, selection=selection, replay=replay)
        writer = SuiteResultLog(store)
        def observe(event):
            writer.append_event(event)
            if on_event:
                on_event(event)

        try:
            if on_runner:
                on_runner(runner)
            if command_id:
                store.append({'event': 'command_started', 'command_id': command_id, 'status': 'running'})
            store.append({'event': 'suite_resumed', 'selection': None if selection is None else sorted(selection)})
            if run_control is not None:
                run_control.check()
            if all(len(seeds[agent.agent_id].results) == agent.case_count for agent in store.registrations):
                from agentbench.harness.result import SuiteAgentResult
                result = BenchmarkSuiteResult(store.suite_id, tuple(seeds), tuple(
                    SuiteAgentResult(agent.agent_id, tuple(seeds[agent.agent_id].results[index]
                        for index in sorted(seeds[agent.agent_id].results)), agent.case_count)
                    for agent in store.registrations))
            else:
                result = runner.run(store.registrations, suite_id=store.suite_id, resume_state=seeds,
                                    retain_case=store.retain_case, on_event=observe,
                                    **({'run_control': run_control} if run_control is not None else {}))
            writer.append_partial_results(result.items)
            writer.append_suite_complete(result)
            if command_id:
                store.append({'event': 'command_completed', 'command_id': command_id, 'status': 'completed'})
            return result
        except BaseException as exc:
            writer.append_partial_results(getattr(exc, 'partial_items', ()))
            writer.append_suite_error(exc)
            if command_id:
                store.append({'event': 'command_rejected', 'command_id': command_id,
                              'status': 'rejected', 'error': str(exc)})
            raise
        finally:
            if on_runner:
                on_runner(None)
