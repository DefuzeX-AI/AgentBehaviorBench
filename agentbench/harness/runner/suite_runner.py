"""

Run an evaluation SDK benchmark suite across registered agents.


"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from uuid import uuid4

from ..errors import ProviderSelectionError, SuiteConfigurationError
from ..progress import ProgressCallback, emit_progress
from ..protocols import SDK
from ..registry import AgentRegistration
from ..result import BenchmarkSuiteResult, SuiteAgentResult
from .benchmark_runner import (
    BenchmarkRunner,
    StepCompleteCallback,
    StepFailureCallback,
    StepStartCallback,
)


class SuiteRunner:
    """

    Sequentially execute one benchmark for every selected Agent.

    create suit -> run benchmark for each agent -> collect results -> return suite result

    """

    def __init__(
        self,
        *,
        sdk: SDK | None = None,
        sdk_options: Mapping[str, object] | None = None,
        benchmark_runner: BenchmarkRunner | None = None,
    ) -> None:
        if benchmark_runner is not None and (
            sdk is not None or sdk_options is not None
        ):
            raise ValueError(
                "Configure sdk on either SuiteRunner or benchmark_runner, not both"
            )
        if benchmark_runner is None and sdk is None:
            from agentbench.evaluation.benchmark import ContainerBenchmarkRunner
            benchmark_runner = ContainerBenchmarkRunner(options=sdk_options)
        self._benchmark_runner = benchmark_runner or BenchmarkRunner(sdk=sdk, sdk_options=sdk_options)

    @staticmethod
    def new_suite_id() -> str:
        """Return an ID for one benchmark suite execution."""

        return f"suite_{uuid4().hex}"

    def run(
        self, registrations: Iterable[AgentRegistration], **kwargs: object
    ) -> BenchmarkSuiteResult:
        """Run a suite with the injected SDK and common progress callbacks.

        Configure SDK-specific options in the constructor's sdk_options.
        """
        allowed = {
            "suite_id",
            "continue_on_error",
            "on_agent_start",
            "on_agent_complete",
            "on_progress",
            "on_step_start",
            "on_step_complete",
            "on_step_failure",
        }
        unexpected = set(kwargs) - allowed
        if unexpected:
            raise TypeError(
                f"Pass SDK settings via sdk_options; unsupported run options: {sorted(unexpected)}"
            )
        return self._run_suite(registrations, _use_sdk=True, **kwargs)

    def run_defuzex(
        self, registrations: Iterable[AgentRegistration], **kwargs: object
    ) -> BenchmarkSuiteResult:
        """Compatibility entry point for the original DefuzeX options."""
        return self._run_suite(registrations, **kwargs)

    def _run_suite(
        self,
        registrations: Iterable[AgentRegistration],
        *,
        _use_sdk: bool = False,
        case_provider: object | None = None,
        judge_provider: object | None = None,
        api_key: str | None = None,
        suite_id: str | None = None,
        max_inputs: int | None = None,
        allow_local: bool = False,
        track_files: bool = True,
        save_local: bool = False,
        continue_on_error: bool = True,
        on_agent_start: (Callable[[AgentRegistration, int, int], None] | None) = None,
        on_agent_complete: Callable[[SuiteAgentResult], None] | None = None,
        on_progress: ProgressCallback | None = None,
        on_step_start: StepStartCallback | None = None,
        on_step_complete: StepCompleteCallback | None = None,
        on_step_failure: StepFailureCallback | None = None,
    ) -> BenchmarkSuiteResult:
        """Run selected Agents and retain both reports and execution errors."""

        if suite_id is None:
            suite_id = self.new_suite_id()
        elif not suite_id.strip():
            raise ValueError("Suite ID cannot be empty")
        selected = tuple(registrations)
        self._validate_selection(selected)
        items: list[SuiteAgentResult] = []

        emit_progress(
            on_progress,
            stage="sdk_check",
            status="started",
        )
        try:
            if _use_sdk:
                provider_mode = self._benchmark_runner.validate_sdk(selected[0])
            else:
                provider_mode = self._benchmark_runner.validate_defuzex(
                    selected[0],
                    case_provider=case_provider,
                    judge_provider=judge_provider,
                    api_key=api_key,
                    max_inputs=max_inputs,
                    allow_local=allow_local,
                    track_files=track_files,
                    save_local=save_local,
                )
        except Exception as exc:
            emit_progress(
                on_progress,
                stage="sdk_check",
                status="failed",
                detail=_error_detail(exc),
            )
            raise SuiteConfigurationError(str(exc)) from exc
        emit_progress(
            on_progress,
            stage="sdk_check",
            status="succeeded",
            detail=f"Provider mode: {provider_mode}",
        )

        for index, registration in enumerate(selected, start=1):
            if on_agent_start is not None:
                on_agent_start(registration, index, len(selected))

            benchmarks = []
            run_error: Exception | None = None
            for _ in range(registration.case_count):
                try:
                    if _use_sdk:
                        benchmark = self._benchmark_runner.run(
                            registration,
                            on_progress=on_progress,
                            on_step_start=on_step_start,
                            on_step_complete=on_step_complete,
                            on_step_failure=on_step_failure,
                        )
                    else:
                        benchmark = self._benchmark_runner.run_defuzex(
                            registration,
                            case_provider=case_provider,
                            judge_provider=judge_provider,
                            api_key=api_key,
                            max_inputs=max_inputs,
                            allow_local=allow_local,
                            track_files=track_files,
                            save_local=save_local,
                            on_progress=on_progress,
                            on_step_start=on_step_start,
                            on_step_complete=on_step_complete,
                            on_step_failure=on_step_failure,
                        )
                except ProviderSelectionError as exc:
                    # Provider selection is shared suite configuration, so retrying
                    # it for every Agent cannot produce a different result.
                    raise SuiteConfigurationError(str(exc)) from exc
                except Exception as exc:
                    run_error = exc
                    break
                benchmarks.append(benchmark)

            item = SuiteAgentResult(
                agent_id=registration.agent_id,
                benchmarks=tuple(benchmarks),
                requested_case_count=registration.case_count,
                error_type=None if run_error is None else type(run_error).__name__,
                error_message=None if run_error is None else str(run_error),
            )

            items.append(item)
            if on_agent_complete is not None:
                on_agent_complete(item)
            if not item.passed and not continue_on_error:
                break

        return BenchmarkSuiteResult(
            suite_id=suite_id,
            selected_agent_ids=tuple(agent.agent_id for agent in selected),
            items=tuple(items),
        )

    @staticmethod
    def _validate_selection(
        registrations: tuple[AgentRegistration, ...],
    ) -> None:
        if not registrations:
            raise ValueError("A benchmark suite requires at least one Agent")

        agent_ids = tuple(agent.agent_id for agent in registrations)
        if len(set(agent_ids)) != len(agent_ids):
            raise ValueError("A benchmark suite cannot contain duplicate Agent IDs")


def _error_detail(exc: Exception) -> str:
    message = str(exc).strip()
    return type(exc).__name__ if not message else f"{type(exc).__name__}: {message}"
