"""Prepare Agent batches and execute independent Cases through one bounded pool."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict
import threading
from types import MappingProxyType
from uuid import uuid4

from agentbench.sdk.contracts import EvaluationRunner, PreparedCase, SDK

from ..concurrency import ConcurrencySettings
from ..errors import SuiteConfigurationError
from ..events import EventBus, QueuedTraceSink
from ..jobs import CaseJob, PreparationJob, SuiteCallbacks
from ..progress import BenchmarkProgress
from ..registry import AgentRegistration
from ..result import BenchmarkSuiteResult
from ..scheduler import CaseScheduler
from ..scheduling import RetryPolicy


class SuiteRunner:
    """One Suite owns factories, cancellation, Case dispatch and ordered results."""

    def __init__(self, *, sdk: SDK | None = None,
                 sdk_options: Mapping[str, object] | None = None,
                 benchmark_runner: EvaluationRunner | None = None,
                 runner_factory=None, concurrency: ConcurrencySettings | None = None,
                 trace_sink=None, retry_policy: RetryPolicy | None = None) -> None:
        if (benchmark_runner is not None or runner_factory is not None) and (
            sdk is not None or sdk_options is not None
        ):
            raise ValueError("Configure SDK on the supplied runner/factory or SuiteRunner, not both")
        if benchmark_runner is not None and runner_factory is not None:
            raise ValueError("Pass benchmark_runner or runner_factory, not both")
        if concurrency is not None and not isinstance(concurrency, ConcurrencySettings):
            raise TypeError("concurrency must be ConcurrencySettings")

        
        self.concurrency = concurrency or ConcurrencySettings()
        self._trace_sink = trace_sink
        self._run_lock = threading.Lock()
        self._active_control = None
        self.retry_policy = retry_policy or RetryPolicy()

        
        if benchmark_runner is None and runner_factory is None:
            from agentbench.runtime.interception import DEFAULT_TRACE_MAX_BYTES, NullTraceSink
            from agentbench.sdk.plugins import evaluation_plan
            from agentbench.sdk.runtime import build_evaluation_runner_factory


            runner_factory = build_evaluation_runner_factory(
                evaluation_plan(sdk=sdk, options=sdk_options), model=None,
                trace_sink=trace_sink or NullTraceSink(), trace_max_bytes=DEFAULT_TRACE_MAX_BYTES)
        self._benchmark_runner = benchmark_runner
        self._runner_factory = runner_factory

    @staticmethod
    def new_suite_id() -> str:
        return f"suite_{uuid4().hex}"

    def cancel(self, *, force: bool = False) -> None:
        control = self._active_control
        if control is not None:
            control.force_cancel() if force else control.cancel()

    def run(self, registrations: Iterable[AgentRegistration], *, suite_id=None,
            continue_on_error=True, on_agent_start=None, on_agent_complete=None,
            on_progress=None, on_step_start=None, on_step_complete=None,
            on_step_failure=None, on_event=None, on_tick=None, resume_state=None,
            retain_case=None, retry_policy=None, run_control=None) -> BenchmarkSuiteResult:
        """Run one Suite: validate Agents, prepare Cases, schedule jobs, and collect results.

        This method waits for the Suite to finish. CaseScheduler creates the
        worker thread pool; the setup below does not start Case worker threads.
        Worker events are delivered through EventBus to callbacks on the
        coordinating thread. Optional callbacks default to None (no handler).

        Args:
            registrations: Iterable of AgentRegistration objects selected by
                the caller. Each registration supplies an agent_id and a
                positive case_count. The selection must be nonempty and IDs
                must be unique. Its order is retained in the Suite result.
            suite_id: Nonempty string identifying this Suite in events and
                results. None generates a new ID; an existing ID is reused.
            continue_on_error: Whether to keep scheduling after ordinary job
                failures. False stops new admissions after a failure; shared
                infrastructure failures and cancellation can stop the Suite
                regardless of this option.
            on_agent_start: Callback(agent, index, total). Receives the Agent
                registration, its one-based selection index, and Agent count.
            on_agent_complete: Callback(item). Receives a SuiteAgentResult
                when an Agent reaches its terminal outcome, including failure.
            on_progress: Callback(event). Receives a BenchmarkProgress object
                describing a stage, status, and available task identity.
            on_step_start: Callback(agent_id, input_id, payload). Receives the
                Agent ID, SDK Input ID, and input payload for a Case step.
            on_step_complete: Callback(agent_id, step). Receives the Agent ID
                and a BenchmarkStepResult for a completed step.
            on_step_failure: Callback(agent_id, failure). Receives the Agent ID
                and a BenchmarkStepFailure for a failed step. Step notification
                timing depends on the runner; container runners may replay
                step events from validated artifacts after execution.
            on_event: Callback(event). Receives a dictionary describing a
                Suite/job event, used by the CLI for result logging and output.
            on_tick: Callback() invoked during event-bus draining, including
                while waiting for jobs. Used to flush buffered logs when due;
                this is not a separate timer thread or an exact-time guarantee.
            resume_state: Validated AgentSeed values keyed by Agent ID. Completed
                Cases are retained and prepared Cases skip generation.
            retain_case: Optional Callback(agent_id, PreparedCase) returning a
                durable descriptor before its prepared event is published.
            retry_policy: Optional RetryPolicy override for this invocation.
            run_control: Optional external RunControl preserving cancellation
                requested before this method initializes its runtime resources.

        Returns:
            BenchmarkSuiteResult containing the Suite ID, selected Agent IDs,
            and ordered Agent outcomes with their Case results. A returned
            result can contain failed Cases; returning does not imply a pass.

        Raises:
            ValueError: The Agent selection or Suite ID is invalid.
            SuiteConfigurationError: The runner cannot support the requested
                concurrency, this instance is already running, or SDK/runner
                setup fails validation.
            Other execution, cancellation, callback, or cleanup exceptions may
            propagate. The execution handler preserves available partial_items
            on exceptions and closes the Suite session before releasing its lock.
        """
        from agentbench.runtime.contracts.execution import RunControl

        if run_control is not None and not isinstance(run_control, RunControl):
            raise TypeError('run_control must be a RunControl')

        # Freeze the iterable so validation and scheduling use the same selection.
        selected = tuple(registrations)
        self._validate_selection(selected)

        # Keep the caller's ID so CLI logs and worker events identify one Suite.
        suite_id = self.new_suite_id() if suite_id is None else suite_id

        if not isinstance(suite_id, str) or not suite_id.strip():
            raise ValueError("Suite ID cannot be empty")
        
        # Compute capacity only; the scheduler creates the worker pool later.
        workers = self.concurrency.effective_workers(sum(agent.case_count for agent in selected))
        if workers > 1 and (self._runner_factory is None
                           or not getattr(self._runner_factory, "supports_concurrency", False)):
            raise SuiteConfigurationError(
                "Parallel Cases require a runner factory declaring isolated Cases and cooperative cancellation; "
                "use ABB_MAX_PARALLEL_CASES=1 for this SDK/runner.")
        
        # Reject a second Suite on this instance without waiting. This lock does
        # not prevent independent Cases within the current Suite from overlapping.
        if not self._run_lock.acquire(blocking=False):
            raise SuiteConfigurationError("This SuiteRunner is already running a suite")
        
        # Share one cancellation signal and route worker notifications back to
        # the coordinator instead of calling terminal/log handlers from workers.
        control = run_control if run_control is not None else RunControl()
        self._active_control = control
        bus = EventBus(on_event=on_event, on_tick=on_tick)
        callbacks = SuiteCallbacks(len(selected), on_agent_start, on_agent_complete, on_progress,
                                   on_step_start, on_step_complete, on_step_failure)
        # Track resources, completed outcomes, and the original error for cleanup.
        session = None
        items = ()
        active_error = None
        runners: dict[int, EvaluationRunner] = {}

        try:
            control.check()
            # Materialize sources before opening any SDK runner/session. Custom
            # programmatic registrations need not have a filesystem manifest.
            from agentbench.runtime.source import prepare_agent_source
            for agent in selected:
                if not (agent.path / 'agent.toml').is_file():
                    continue
                def source_progress(message, agent=agent):
                    done = message.endswith(' .... OK')
                    event = BenchmarkProgress('source_preparation', 'succeeded' if done else 'started',
                                              agent_id=agent.agent_id,
                                              detail=message.removesuffix(' .... OK'), suite_id=suite_id)
                    bus.publish({'event': 'progress', **asdict(event)}, on_progress, (event,))
                try:
                    prepare_agent_source(agent.path, check=control.check, output_fn=source_progress)
                except Exception as exc:
                    event = BenchmarkProgress('source_preparation', 'failed', agent_id=agent.agent_id,
                                              detail=str(exc), suite_id=suite_id)
                    bus.publish({'event': 'progress', **asdict(event)}, on_progress, (event,))
                    raise
            if self._runner_factory is not None:
                # Open resources owned by this Suite, using its ID and control.
                session = self._runner_factory.open_suite(suite_id, control)

            def create_runner(registration, identity):
                """Return a task runner for an Agent and its Suite/job identity.

                Queue its trace notifications through this Suite's bus. Factory
                sessions must return a distinct runner object for every task.
                """
                control.check()
                target = self._trace_sink or getattr(self._runner_factory, "trace_sink", None)
                sink = QueuedTraceSink(bus, target, identity)
                
                runner = session.create(registration, identity, sink) if session is not None else self._benchmark_runner
                required = ("validate_sdk", "prepare_cases", "run_case")

                if any(not callable(getattr(runner, name, None)) for name in required):
                    raise SuiteConfigurationError("Evaluation runners must implement validate_sdk, prepare_cases and run_case")
                if session is not None and id(runner) in runners:
                    raise SuiteConfigurationError("runner_factory must return an independent runner for every task")
                runners[id(runner)] = runner
                return runner

            def sdk_progress(status, detail=None):
                """Publish SDK setup status and optional explanatory text."""
                event = BenchmarkProgress("sdk_check", status, detail=detail, suite_id=suite_id)
                bus.publish({"event": "progress", **asdict(event)}, on_progress, (event,))

            # Validate each Agent's SDK setup and describe its preparation job.
            # Creating PreparationJob objects does not generate Cases yet.
            sdk_progress("started")
            preparations = []
            try:
                mode = None
                # Create one Case-preparation job for each selected Agent.
                for index, agent in enumerate(selected):
                    identity = MappingProxyType(dict(
                        suite_id=suite_id, job_id=f"agent_{uuid4().hex}", agent_id=agent.agent_id,
                        registration_index=index, phase="generate", case_index=None, case_id=None))

                    # Create the SDK runner with the Agent's configured Case count.
                    runner = create_runner(agent, identity)
                    # Validate credentials and the Agent's evaluation files.
                    mode = runner.validate_sdk(agent)
                    # Bundle the Agent, runner, and job identity into the preparation queue.
                    preparations.append(PreparationJob(agent, runner, identity))

            except Exception as exc:
                sdk_progress("failed", str(exc))
                raise SuiteConfigurationError(str(exc)) from exc
            sdk_progress("succeeded", f"Provider mode: {mode}")

            # Notify the CLI after all Agent preparation jobs have been queued.
            for job in preparations:
                bus.publish({**job.identity, "event": "agent_queued", "status": "queued",
                             "requested_case_count": job.registration.case_count})

            def create_case_job(preparation: PreparationJob, case: PreparedCase, identity) -> CaseJob:
                """Bind a prepared Case and job identity to its own task runner."""
                runner = create_runner(preparation.registration, identity)
                runner.validate_sdk(preparation.registration)
                return CaseJob(preparation.registration, runner, case, identity)

            # Actual worker scheduling begins here: prepare each Agent's Cases,
            # then execute ready Cases within the shared worker limit.
            # Submit preparation jobs to the worker pool.
            items = CaseScheduler(
                preparations, 
                create_case_job=create_case_job, 
                workers=workers,
                control=control, bus=bus, callbacks=callbacks, continue_on_error=continue_on_error,
                retry_policy=retry_policy or self.retry_policy, seeds=resume_state, retain_case=retain_case,
            ).run()
            
            return BenchmarkSuiteResult(suite_id, tuple(agent.agent_id for agent in selected), items)
        except BaseException as exc:
            # Retain any partial outcomes already attached by the scheduler.
            active_error = exc
            if not hasattr(exc, "partial_items"):
                exc.partial_items = items
            control.cancel()
            raise
        finally:
            # Close Suite resources; preserve the execution error if cleanup
            # also fails. Always release the lock so this instance can run again.
            try:
                if session is not None:
                    try:
                        session.close()
                    except BaseException as cleanup_error:
                        try:
                            bus.publish({"event": "suite_cleanup_failed", "suite_id": suite_id,
                                         "error": {"type": type(cleanup_error).__name__, "message": str(cleanup_error)}})
                        except BaseException:
                            pass
                        if active_error is not None:
                            active_error.cleanup_error = cleanup_error
                        else:
                            cleanup_error.partial_items = items
                            raise
            finally:
                self._active_control = None
                self._run_lock.release()

    @staticmethod
    def _validate_selection(registrations):
        if not registrations:
            raise ValueError("A benchmark suite requires at least one Agent")
        ids = tuple(agent.agent_id for agent in registrations)
        if len(set(ids)) != len(ids):
            raise ValueError("A benchmark suite cannot contain duplicate Agent IDs")
        if any(type(agent.case_count) is not int or agent.case_count < 1 for agent in registrations):
            raise ValueError("Agent case_count must be a positive integer")
