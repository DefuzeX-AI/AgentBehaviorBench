from pathlib import Path

import pytest

from agentbench.adapter import (
    AdapterFactory,
    AdapterInvocation,
    UnsupportedAdapterError,
    create_adapter,
)
from agentbench.adapter.langgraph import LangGraphAdapter
from agentbench.harness.registry import AgentRegistration, AgentRegistry


def test_factory_creates_registered_langgraph_adapter(
    starter_agent: AgentRegistration,
) -> None:
    adapter = create_adapter(starter_agent)

    assert isinstance(adapter, LangGraphAdapter)
    assert not adapter.is_loaded


def test_factory_rejects_unsupported_framework(repo_root: Path) -> None:
    agent = AgentRegistration(
        agent_id="unknown-agent",
        path=repo_root,
        enabled=True,
        status="ready",
        framework="unknown",
        source="",
    )

    with pytest.raises(UnsupportedAdapterError, match="unknown.*langgraph"):
        create_adapter(agent)


def test_factory_can_register_another_adapter_strategy(repo_root: Path) -> None:
    class FakeAdapter:
        @property
        def is_loaded(self) -> bool:
            return True

        def load(self) -> "FakeAdapter":
            return self

        def invoke(
            self, value: object, *, run_config: object | None = None
        ) -> AdapterInvocation:
            return AdapterInvocation(output=value, raw_output=value)

        async def ainvoke(
            self, value: object, *, run_config: object | None = None
        ) -> AdapterInvocation:
            return self.invoke(value, run_config=run_config)

        def close(self) -> None:
            pass

    factory = AdapterFactory({"fake": lambda _: FakeAdapter()})
    agent = AgentRegistration(
        agent_id="fake-agent",
        path=repo_root,
        enabled=True,
        status="ready",
        framework="fake",
        source="",
    )

    adapter = factory.create(agent)

    assert adapter.invoke("hello").output == "hello"
