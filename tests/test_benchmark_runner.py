import pytest

from agentbench.harness import (
    AgentRegistration,
    BenchmarkProgress,
    BenchmarkRunner,
    ProviderSelectionError,
)
from tests.support.results import FakeReport


class FakeInput:
    def __init__(self, input_id: str, payload: object) -> None:
        self.input_id = input_id
        self.payload = payload


class FakeSDKRun:
    def __init__(self) -> None:
        self.run_id = "run_test"
        self.state = "ready"
        self.report: FakeReport | None = None
        self.history: tuple[object, ...] = ()
        self._input = FakeInput("input_test", "DEFUZEX_AGENT_READY")
        self._delivered = False

    def get_input(self, *, full: bool = False) -> FakeInput | None:
        assert full
        if self._delivered:
            return None
        self._delivered = True
        self.state = "input_delivered"
        return self._input

    def submit(
        self,
        output: object = None,
        *,
        status: str = "completed",
        error: str | None = None,
    ) -> FakeReport:
        assert output == "DEFUZEX_AGENT_READY"
        assert status == "completed"
        assert error is None
        self.history = (object(),)
        self.report = FakeReport()
        self.state = "report_ready"
        return self.report


class CapturingRunFactory:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] | None = None

    def __call__(self, **kwargs: object) -> FakeSDKRun:
        self.kwargs = kwargs
        return FakeSDKRun()


class FailingRunFactory:
    def __call__(self, **kwargs: object) -> FakeSDKRun:
        del kwargs
        raise RuntimeError("server unavailable")


class FailingSubmitSDKRun(FakeSDKRun):
    def submit(
        self,
        output: object = None,
        *,
        status: str = "completed",
        error: str | None = None,
    ) -> FakeReport:
        del output, status, error
        raise RuntimeError("judge unavailable")


class FailingSubmitRunFactory:
    def __call__(self, **kwargs: object) -> FakeSDKRun:
        del kwargs
        return FailingSubmitSDKRun()


def test_benchmark_runner_drives_sdk_handshake(
    starter_agent: AgentRegistration,
) -> None:
    sdk_run = FakeSDKRun()

    result = BenchmarkRunner().run(starter_agent, sdk_run)

    assert result.passed
    assert result.agent_id == "test-echo"
    assert result.adapter_name == "LangGraphAdapter"
    assert result.run_state == "report_ready"
    assert result.history_count == 1
    assert len(result.steps) == 1
    assert result.steps[0].input_id == "input_test"
    assert result.steps[0].invocation.output == "DEFUZEX_AGENT_READY"


def test_official_mode_uses_standard_environment_key_and_sdk_judge(
    starter_agent: AgentRegistration,
) -> None:
    factory = CapturingRunFactory()
    runner = BenchmarkRunner(
        sdk_run_factory=factory,
        environ={"DEFUZEX_API_KEY": "dfx_test"},
    )

    result = runner.run_defuzex(
        starter_agent,
        allow_local=True,
        track_files=False,
    )

    assert result.provider_mode == "official"
    assert factory.kwargs is not None
    assert factory.kwargs["api_key"] == "dfx_test"
    assert factory.kwargs["requirement_path"] == starter_agent.requirement_path
    assert "max_inputs" not in factory.kwargs
    assert "case_provider" not in factory.kwargs
    assert "judge_provider" not in factory.kwargs


def test_benchmark_runner_emits_real_lifecycle_order(
    starter_agent: AgentRegistration,
) -> None:
    factory = CapturingRunFactory()
    events: list[BenchmarkProgress] = []
    runner = BenchmarkRunner(
        sdk_run_factory=factory,
        environ={"DEFUZEX_API_KEY": "dfx_test"},
    )

    runner.run_defuzex(
        starter_agent,
        allow_local=True,
        track_files=False,
        on_progress=events.append,
    )

    assert [(event.stage, event.status) for event in events] == [
        ("agent_start", "started"),
        ("agent_start", "succeeded"),
        ("case_generation", "started"),
        ("case_generation", "succeeded"),
        ("benchmark_execution", "started"),
        ("benchmark_execution", "succeeded"),
    ]
    assert events[2].detail == "official"
    assert events[-1].detail == "Judge: pass"


def test_benchmark_runner_emits_step_callbacks(
    starter_agent: AgentRegistration,
) -> None:
    factory = CapturingRunFactory()
    started: list[tuple[str, str, object]] = []
    completed: list[tuple[str, str, object]] = []
    runner = BenchmarkRunner(
        sdk_run_factory=factory,
        environ={"DEFUZEX_API_KEY": "dfx_test"},
    )

    runner.run_defuzex(
        starter_agent,
        allow_local=True,
        track_files=False,
        on_step_start=lambda agent_id, input_id, payload: started.append(
            (agent_id, input_id, payload)
        ),
        on_step_complete=lambda agent_id, step: completed.append(
            (agent_id, step.input_id, step.invocation.output)
        ),
    )

    assert started == [("test-echo", "input_test", "DEFUZEX_AGENT_READY")]
    assert completed == [("test-echo", "input_test", "DEFUZEX_AGENT_READY")]


def test_benchmark_runner_emits_step_failure_after_judge_error(
    starter_agent: AgentRegistration,
) -> None:
    failures = []
    runner = BenchmarkRunner(
        sdk_run_factory=FailingSubmitRunFactory(),
        environ={"DEFUZEX_API_KEY": "dfx_test"},
    )

    with pytest.raises(RuntimeError, match="judge unavailable"):
        runner.run_defuzex(
            starter_agent,
            allow_local=True,
            track_files=False,
            on_step_failure=lambda agent_id, failure: failures.append(
                (agent_id, failure)
            ),
        )

    assert len(failures) == 1
    agent_id, failure = failures[0]
    assert agent_id == "test-echo"
    assert failure.input_id == "input_test"
    assert failure.payload == "DEFUZEX_AGENT_READY"
    assert failure.output == "DEFUZEX_AGENT_READY"
    assert failure.error_type == "RuntimeError"
    assert failure.error_message == "judge unavailable"


def test_benchmark_runner_reports_case_generation_failure(
    starter_agent: AgentRegistration,
) -> None:
    events: list[BenchmarkProgress] = []
    runner = BenchmarkRunner(
        sdk_run_factory=FailingRunFactory(),
        environ={"DEFUZEX_API_KEY": "dfx_test"},
    )

    with pytest.raises(RuntimeError, match="server unavailable"):
        runner.run_defuzex(
            starter_agent,
            allow_local=True,
            track_files=False,
            on_progress=events.append,
        )

    assert [(event.stage, event.status) for event in events] == [
        ("agent_start", "started"),
        ("agent_start", "succeeded"),
        ("case_generation", "started"),
        ("case_generation", "failed"),
    ]
    assert events[-1].detail == "RuntimeError: server unavailable"


def test_explicit_requirement_path_overrides_registered_default(
    starter_agent: AgentRegistration,
) -> None:
    factory = CapturingRunFactory()
    runner = BenchmarkRunner(
        sdk_run_factory=factory,
        environ={"DEFUZEX_API_KEY": "dfx_test"},
    )

    runner.run_defuzex(
        starter_agent,
        requirement_path="override-requirement.md",
        allow_local=True,
        track_files=False,
    )

    assert factory.kwargs is not None
    assert factory.kwargs["requirement_path"] == "override-requirement.md"


def test_explicit_provider_pair_selects_local_mode(
    starter_agent: AgentRegistration,
) -> None:
    factory = CapturingRunFactory()
    case_provider = object()
    judge_provider = object()
    runner = BenchmarkRunner(
        sdk_run_factory=factory,
        environ={"DEFUZEX_API_KEY": "dfx_test"},
    )

    result = runner.run_defuzex(
        starter_agent,
        case_provider=case_provider,
        judge_provider=judge_provider,
        max_inputs=1,
        allow_local=True,
        track_files=False,
    )

    assert result.provider_mode == "local"
    assert factory.kwargs is not None
    assert factory.kwargs["case_provider"] is case_provider
    assert factory.kwargs["judge_provider"] is judge_provider
    assert factory.kwargs["max_inputs"] == 1
    assert "api_key" not in factory.kwargs
    assert "requirement_path" not in factory.kwargs


def test_missing_key_and_providers_stops_before_run_creation(
    starter_agent: AgentRegistration,
) -> None:
    factory = CapturingRunFactory()
    runner = BenchmarkRunner(sdk_run_factory=factory, environ={})

    with pytest.raises(ProviderSelectionError, match="DEFUZEX_API_KEY"):
        runner.run_defuzex(
            starter_agent,
            requirement_path="requirement.md",
            allow_local=True,
        )

    assert factory.kwargs is None


def test_partial_local_provider_pair_is_rejected(
    starter_agent: AgentRegistration,
) -> None:
    factory = CapturingRunFactory()
    runner = BenchmarkRunner(sdk_run_factory=factory, environ={})

    with pytest.raises(
        ProviderSelectionError,
        match="both case_provider and judge_provider",
    ):
        runner.run_defuzex(
            starter_agent,
            case_provider=object(),
            max_inputs=1,
            allow_local=True,
        )

    assert factory.kwargs is None
