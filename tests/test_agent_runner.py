import pytest

from agentbench.harness import (
    AgentNotRunningError,
    AgentRegistration,
    AgentRunner,
    AgentStartError,
)


def test_runner_starts_invokes_and_stops_langgraph_agent(
    starter_agent: AgentRegistration,
) -> None:
    running = AgentRunner().start(starter_agent)

    assert running.agent_id == "test-echo"
    assert running.adapter_name == "LangGraphAdapter"
    assert running.is_running
    assert running.invoke("DEFUZEX_AGENT_READY").output == "DEFUZEX_AGENT_READY"

    running.stop()
    assert not running.is_running

    with pytest.raises(AgentNotRunningError):
        running.invoke("after stop")


def test_running_agent_context_manager_stops_agent(
    starter_agent: AgentRegistration,
) -> None:
    with AgentRunner().start(starter_agent) as running:
        assert running.is_running

    assert not running.is_running


def test_runner_surfaces_the_underlying_start_failure(
    starter_agent: AgentRegistration,
) -> None:
    class FailingAdapter:
        def load(self) -> None:
            raise ValueError("OPENROUTER_MODEL is missing")

        def close(self) -> None:
            pass

    class FailingRuntimeFactory:
        def create_adapter(self, *args: object, **kwargs: object) -> FailingAdapter:
            return FailingAdapter()

    runner = AgentRunner(runtime_factory=FailingRuntimeFactory())  # type: ignore[arg-type]

    with pytest.raises(
        AgentStartError,
        match="ValueError: OPENROUTER_MODEL is missing",
    ):
        runner.start(starter_agent)
