"""Execute SDK runs through registered agents."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from pathlib import Path

from ..errors import AgentInvocationError, ProviderSelectionError
from ..progress import ProgressCallback, emit_progress
from ..protocols import SDK, SDKReport, SDKRun, SDKRunFactory
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
        sdk_run_factory: SDKRunFactory | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        if sdk is not None and sdk_run_factory is not None:
            raise ValueError("Pass sdk or sdk_run_factory, not both")
        self._sdk = sdk
        self._sdk_options = dict(sdk_options or {})
        self._agent_runner = agent_runner or AgentRunner()
        self._sdk_run_factory = sdk_run_factory
        self._environ = os.environ if environ is None else environ

    def run_defuzex(
        self,
        registration: AgentRegistration,
        *,
        requirement_path: str | Path | None = None,
        case_provider: object | None = None,
        judge_provider: object | None = None,
        api_key: str | None = None,
        max_inputs: int | None = None,
        allow_local: bool = False,
        track_files: bool = True,
        save_local: bool = False,
        on_progress: ProgressCallback | None = None,
        on_step_start: StepStartCallback | None = None,
        on_step_complete: StepCompleteCallback | None = None,
        on_step_failure: StepFailureCallback | None = None,
    ) -> BenchmarkResult:
        """Start one Agent, create its SDK Run, and execute the handshake."""

        from agentbench.sdk.defuzex import create_run

        provider_mode, run_kwargs = self._prepare_defuzex(
            registration=registration,
            requirement_path=requirement_path,
            case_provider=case_provider,
            judge_provider=judge_provider,
            api_key=api_key,
            max_inputs=max_inputs,
            allow_local=allow_local,
            track_files=track_files,
            save_local=save_local,
        )

        return self._execute(
            registration,
            create_run=lambda: (self._sdk_run_factory or create_run)(**run_kwargs),
            provider_mode=provider_mode,
            on_progress=on_progress,
            on_step_start=on_step_start,
            on_step_complete=on_step_complete,
            on_step_failure=on_step_failure,
        )

    def _execute(
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
        with running:
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
                result = self._run_with_running(
                    registration,
                    sdk_run,
                    running,
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

    def run(
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
        added to that path. Omitting sdk preserves the DefuzeX default.
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
            with self._agent_runner.start(registration) as running:
                return self._run_with_running(
                    registration,
                    sdk_run,
                    running,
                    on_step_start=on_step_start,
                    on_step_complete=on_step_complete,
                    on_step_failure=on_step_failure,
                )
        if self._sdk is None:
            return self.run_defuzex(registration, **self._sdk_options, **callbacks)
        mode = self.validate_sdk(registration)
        kwargs = {"repo_path": registration.path, **self._sdk_options}
        return self._execute(
            registration,
            create_run=lambda: self._sdk.create_run(**kwargs),
            provider_mode=mode,
            **callbacks,
        )

    def validate_sdk(self, registration: AgentRegistration) -> str:
        """Check the selected SDK interface without starting an Agent or Run."""
        if self._sdk is None:
            return self.validate_defuzex(registration, **self._sdk_options)
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

    def validate_defuzex(
        self,
        registration: AgentRegistration,
        *,
        requirement_path: str | Path | None = None,
        case_provider: object | None = None,
        judge_provider: object | None = None,
        api_key: str | None = None,
        max_inputs: int | None = None,
        allow_local: bool = False,
        track_files: bool = True,
        save_local: bool = False,
    ) -> str:
        """Validate shared SDK and Provider configuration without networking."""

        provider_mode, _ = self._prepare_defuzex(
            registration=registration,
            requirement_path=requirement_path,
            case_provider=case_provider,
            judge_provider=judge_provider,
            api_key=api_key,
            max_inputs=max_inputs,
            allow_local=allow_local,
            track_files=track_files,
            save_local=save_local,
        )
        return provider_mode

    def _run_with_running(
        self,
        registration: AgentRegistration,
        sdk_run: SDKRun,
        running: RunningAgent,
        *,
        on_step_start: StepStartCallback | None = None,
        on_step_complete: StepCompleteCallback | None = None,
        on_step_failure: StepFailureCallback | None = None,
    ) -> BenchmarkResult:
        """Execute an SDK handshake through an Agent that is already running."""

        steps: list[BenchmarkStepResult] = []
        report: SDKReport | None = None
        run_config = {"configurable": {"thread_id": sdk_run.run_id}}

        adapter_name = running.adapter_name
        while (test_input := sdk_run.get_input(full=True)) is not None:
            if on_step_start is not None:
                on_step_start(
                    registration.agent_id,
                    test_input.input_id,
                    test_input.payload,
                )
            try:
                invocation = running.invoke(
                    test_input.payload,
                    run_config=run_config,
                )
            except Exception as exc:
                if on_step_failure is not None:
                    on_step_failure(
                        registration.agent_id,
                        _step_failure(test_input.input_id, test_input.payload, exc),
                    )
                self._record_failed_submission(sdk_run, exc)
                raise AgentInvocationError(
                    f"Agent {registration.agent_id!r} failed for "
                    f"SDK Input {test_input.input_id!r}"
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

    def _prepare_defuzex(
        self,
        *,
        registration: AgentRegistration,
        requirement_path: str | Path | None,
        case_provider: object | None,
        judge_provider: object | None,
        api_key: str | None,
        max_inputs: int | None,
        allow_local: bool,
        track_files: bool,
        save_local: bool,
    ) -> tuple[str, dict[str, object]]:
        from agentbench.sdk.defuzex import DefuzeConfiguration, validate_installation

        if self._sdk is not None:
            raise ValueError("Use run() and validate_sdk() with an injected sdk")
        provider_mode, run_kwargs = DefuzeConfiguration(self._environ).prepare(
            registration=registration,
            requirement_path=requirement_path,
            case_provider=case_provider,
            judge_provider=judge_provider,
            api_key=api_key,
            max_inputs=max_inputs,
            allow_local=allow_local,
            track_files=track_files,
            save_local=save_local,
        )
        if self._sdk_run_factory is None:
            validate_installation(provider_mode, run_kwargs)
        return provider_mode, run_kwargs

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


def _error_detail(exc: Exception) -> str:
    message = str(exc).strip()
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
        error_message=str(exc),
    )
