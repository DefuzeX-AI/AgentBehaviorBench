"""Execute SDK runs through registered agents."""

from __future__ import annotations

import os
import asyncio
from collections.abc import Callable, Mapping
from pathlib import Path

from ..errors import AgentInvocationError, ProviderSelectionError
from ..progress import ProgressCallback, emit_progress
from agentbench.sdk.contracts import PreparedCase, SDK, SDKReport, SDKRun
from agentbench.runtime.contracts.execution import RunControl
from ..registry import AgentRegistration
from ..result import BenchmarkResult, BenchmarkStepFailure, BenchmarkStepResult
from .agent_runner import AgentRunner
from .running_agent import RunningAgent

StepStartCallback = Callable[[str, str, object], None]
StepCompleteCallback = Callable[[str, BenchmarkStepResult], None]
StepFailureCallback = Callable[[str, BenchmarkStepFailure], None]


class BenchmarkRunner:
    """Drive one compatible SDK Run through a registered agent."""

    def __init__(
        self,
        *,
        sdk: SDK | None = None,
        sdk_options: Mapping[str, object] | None = None,
        agent_runner: AgentRunner | None = None,
        environ: Mapping[str, str] | None = None,
        observation_factory=None,
        control: RunControl | None = None,
    ) -> None:
        self._observation_factory = observation_factory
        self._sdk = sdk
        self._sdk_options = dict(sdk_options or {})
        self._agent_runner = agent_runner or AgentRunner()
        self._environ = dict(os.environ if environ is None else environ)
        self._control = control or RunControl()

    def run(self, *args, **kwargs) -> BenchmarkResult:
        """Synchronous entry; all Inputs and cleanup share one event loop."""
        return _run_sync(self.arun, *args, **kwargs)

    def prepare_cases(self, registration: AgentRegistration, *, on_progress=None) -> tuple[PreparedCase, ...]:
        """Describe independent SDK Run requests without starting an Agent."""
        self._control.check()
        self.validate_sdk(registration)
        return tuple(PreparedCase(index) for index in range(registration.case_count))

    def run_case(self, registration: AgentRegistration, case: PreparedCase, *,
                 on_progress=None, on_step_start=None, on_step_complete=None,
                 on_step_failure=None) -> BenchmarkResult:
        """Create and execute one SDK Run for the selected Case work item."""
        self._control.check()
        if not isinstance(case, PreparedCase):
            raise TypeError('run_case requires a PreparedCase')
        if case.case_index >= registration.case_count:
            raise ValueError('Prepared Case index exceeds the registered Case count')
        return self.run(registration, on_progress=on_progress, on_step_start=on_step_start,
                        on_step_complete=on_step_complete, on_step_failure=on_step_failure)

    async def _execute(
        self,
        registration: AgentRegistration,
        *,
        create_run: Callable[[], SDKRun],
        provider_mode: str,
        on_progress: ProgressCallback | None = None,
        on_step_start: StepStartCallback | None = None,
        on_step_complete: StepCompleteCallback | None = None,
        on_step_failure: StepFailureCallback | None = None,
    ) -> BenchmarkResult:
        self._control.check()
        emit_progress(
            on_progress,
            stage="agent_start",
            status="started",
            agent_id=registration.agent_id,
        )
        try:
            running = self._agent_runner.start(registration)
        except Exception as exc:
            emit_progress(
                on_progress,
                stage="agent_start",
                status="failed",
                agent_id=registration.agent_id,
                detail=_error_detail(exc),
            )
            raise

        emit_progress(
            on_progress,
            stage="agent_start",
            status="succeeded",
            agent_id=registration.agent_id,
            detail=running.adapter_name,
        )
        async with running:
            emit_progress(
                on_progress,
                stage="case_generation",
                status="started",
                agent_id=registration.agent_id,
                detail=provider_mode,
            )
            try:
                sdk_run = create_run()
            except Exception as exc:
                emit_progress(
                    on_progress,
                    stage="case_generation",
                    status="failed",
                    agent_id=registration.agent_id,
                    detail=_error_detail(exc),
                )
                raise

            emit_progress(
                on_progress,
                stage="case_generation",
                status="succeeded",
                agent_id=registration.agent_id,
                detail=f"run={sdk_run.run_id}",
            )
            emit_progress(
                on_progress,
                stage="benchmark_execution",
                status="started",
                agent_id=registration.agent_id,
            )
            try:
                result = await self._run_with_running(
                    registration,
                    sdk_run,
                    running,
                    on_progress=on_progress,
                    on_step_start=on_step_start,
                    on_step_complete=on_step_complete,
                    on_step_failure=on_step_failure,
                )
            except Exception as exc:
                emit_progress(
                    on_progress,
                    stage="benchmark_execution",
                    status="failed",
                    agent_id=registration.agent_id,
                    detail=_error_detail(exc),
                )
                raise

            judge_status = (
                result.report.status if result.report is not None else "no report"
            )
            emit_progress(
                on_progress,
                stage="benchmark_execution",
                status="succeeded",
                agent_id=registration.agent_id,
                detail=f"Judge: {judge_status}",
            )

        return BenchmarkResult(
            agent_id=result.agent_id,
            adapter_name=result.adapter_name,
            run_id=result.run_id,
            run_state=result.run_state,
            report=result.report,
            steps=result.steps,
            history_count=result.history_count,
            provider_mode=provider_mode,
        )

    async def arun(
        self,
        registration: AgentRegistration,
        sdk_run: SDKRun | None = None,
        *,
        on_progress: ProgressCallback | None = None,
        on_step_start: StepStartCallback | None = None,
        on_step_complete: StepCompleteCallback | None = None,
        on_step_failure: StepFailureCallback | None = None,
    ) -> BenchmarkResult:
        """Create a Run using sdk=..., or execute an already-created SDKRun.

        A supplied SDK receives repo_path plus sdk_options unchanged. It owns
        credentials, providers, validation and judging. No DefuzeX settings are
        added to that path. Use SuiteRunner for directory-discovered adapters;
        this lower-level runner requires an SDK object or an existing SDKRun.
        """
        callbacks = dict(
            on_progress=on_progress,
            on_step_start=on_step_start,
            on_step_complete=on_step_complete,
            on_step_failure=on_step_failure,
        )
        if sdk_run is not None:
            if self._sdk is not None or self._sdk_options:
                raise ValueError(
                    "An existing sdk_run cannot be combined with sdk or sdk_options"
                )
            async with self._agent_runner.start(registration) as running:
                return await self._run_with_running(
                    registration,
                    sdk_run,
                    running,
                    on_progress=on_progress,
                    on_step_start=on_step_start,
                    on_step_complete=on_step_complete,
                    on_step_failure=on_step_failure,
                )
        mode = self.validate_sdk(registration)
        kwargs = {"repo_path": registration.path, **self._sdk_options}
        return await self._execute(
            registration,
            create_run=lambda: self._sdk.create_run(**kwargs),
            provider_mode=mode,
            **callbacks,
        )

    def validate_sdk(self, registration: AgentRegistration) -> str:
        """Check the selected SDK interface without starting an Agent or Run."""
        if self._sdk is None:
            raise ProviderSelectionError(
                "BenchmarkRunner requires an explicit SDK object; use SuiteRunner "
                "for directory-discovered adapters, or pass an existing SDKRun to run()."
            )
        if isinstance(self._sdk, type) or not callable(
            getattr(self._sdk, "create_run", None)
        ):
            raise ProviderSelectionError(
                "sdk must provide a callable create_run(**options)"
            )
        if "repo_path" in self._sdk_options:
            raise ProviderSelectionError(
                "repo_path is supplied per Agent; omit it from sdk_options"
            )
        return "custom"

    async def _run_with_running(
        self,
        registration: AgentRegistration,
        sdk_run: SDKRun,
        running: RunningAgent,
        *,
        on_progress: ProgressCallback | None = None,
        on_step_start: StepStartCallback | None = None,
        on_step_complete: StepCompleteCallback | None = None,
        on_step_failure: StepFailureCallback | None = None,
    ) -> BenchmarkResult:
        """Execute an SDK handshake through an Agent that is already running."""

        observed = self._observation_factory(registration, sdk_run) if self._observation_factory else None
        if observed:
            emit_progress(on_progress, stage="benchmark_execution", status="started",
                          agent_id=registration.agent_id, artifact_directory=str(observed.directory))
        try:
            result = await self._drive_inputs(registration, sdk_run, running, observation=observed,
                on_step_start=on_step_start, on_step_complete=on_step_complete, on_step_failure=on_step_failure)
        except BaseException as exc:
            if observed:
                observed.finish(error=exc)
            raise
        if observed:
            observed.finish(result=result)
        return result

    async def _drive_inputs(
        self,
        registration: AgentRegistration,
        sdk_run: SDKRun,
        running: RunningAgent,
        *,
        observation=None,
        on_step_start: StepStartCallback | None = None,
        on_step_complete: StepCompleteCallback | None = None,
        on_step_failure: StepFailureCallback | None = None,
    ) -> BenchmarkResult:
        """Execute an SDK handshake through an Agent that is already running."""

        steps: list[BenchmarkStepResult] = []
        report: SDKReport | None = None
        run_config = {"configurable": {"thread_id": sdk_run.run_id}}

        adapter_name = running.adapter_name
        while True:
            self._control.check()
            test_input = sdk_run.get_input(full=True)
            if test_input is None:
                break
            if on_step_start is not None:
                on_step_start(
                    registration.agent_id,
                    test_input.input_id,
                    test_input.payload,
                )
            try:
                if observation:
                    invocation = await observation.invoke(running, test_input, run_config)
                else:
                    invocation = await running.ainvoke(test_input.payload, run_config=run_config)
            except Exception as exc:
                if on_step_failure is not None:
                    on_step_failure(
                        registration.agent_id,
                        _step_failure(test_input.input_id, test_input.payload, exc),
                    )
                self._record_failed_submission(sdk_run, exc)
                raise AgentInvocationError(
                    f"Agent {registration.agent_id!r} failed for "
                    f"SDK Input {test_input.input_id!r}: {_error_detail(exc)}"
                ) from exc

            step = BenchmarkStepResult(
                input_id=test_input.input_id,
                payload=test_input.payload,
                invocation=invocation,
            )
            try:
                report = sdk_run.submit(invocation.output)
            except Exception as exc:
                if on_step_failure is not None:
                    on_step_failure(
                        registration.agent_id,
                        _step_failure(
                            test_input.input_id,
                            test_input.payload,
                            exc,
                            output=invocation.output,
                            raw_output=invocation.raw_output,
                        ),
                    )
                raise

            steps.append(step)
            if on_step_complete is not None:
                on_step_complete(registration.agent_id, step)

        if report is None:
            report = sdk_run.report
        return BenchmarkResult(
            agent_id=registration.agent_id,
            adapter_name=adapter_name,
            run_id=sdk_run.run_id,
            run_state=sdk_run.state,
            report=report,
            steps=tuple(steps),
            history_count=len(sdk_run.history),
        )

    @staticmethod
    def _record_failed_submission(sdk_run: SDKRun, exc: Exception) -> None:
        """Best-effort recording keeps SDK history truthful on agent failure."""

        try:
            sdk_run.submit(
                status="failed",
                error=f"Agent invocation failed: {type(exc).__name__}",
            )
        except Exception:
            pass


def _error_message(exc: Exception) -> str:
    from agentbench.observe.store import environment_secrets, redact
    return redact(str(exc), environment_secrets())


def _error_detail(exc: Exception) -> str:
    message = _error_message(exc).strip()
    return type(exc).__name__ if not message else f"{type(exc).__name__}: {message}"


def _step_failure(
    input_id: str,
    payload: object,
    exc: Exception,
    *,
    output: object | None = None,
    raw_output: object | None = None,
) -> BenchmarkStepFailure:
    return BenchmarkStepFailure(
        input_id=input_id,
        payload=payload,
        output=output,
        raw_output=raw_output,
        error_type=type(exc).__name__,
        error_message=_error_message(exc),
    )


def _run_sync(method, *args, **kwargs):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(method(*args, **kwargs))
    raise RuntimeError("A loop is already running; await BenchmarkRunner.arun() instead")
