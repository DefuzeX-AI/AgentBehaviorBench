from pathlib import Path
from dataclasses import replace

import pytest

from agentbench.harness import AgentRegistration, AgentRegistry, load_registry


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def registry(repo_root: Path) -> AgentRegistry:
    return load_registry(repo_root / "resources" / "registry.toml")


@pytest.fixture(scope="session")
def starter_agent(tmp_path_factory: pytest.TempPathFactory) -> AgentRegistration:
    """Use a tiny offline graph, independent of downloaded Agent projects."""
    root = tmp_path_factory.mktemp("echo-graph")
    source = root / "agent"
    source.mkdir()
    (root / "agent.toml").write_text(
        'agent_id = "test-echo"\n'
        '[adapter]\ntype = "langgraph"\nmode = "in_process"\n'
        'config = "langgraph.json"\ngraph_id = "agent"\n'
        'input_key = "prompt"\noutput_key = "response"\n', encoding="utf-8"
    )
    (source / "langgraph.json").write_text(
        '{"graphs": {"agent": "./graph.py:graph"}}', encoding="utf-8"
    )
    (source / "graph.py").write_text(
        'from typing_extensions import TypedDict\n'
        'from langgraph.graph import StateGraph, START, END\n'
        'class State(TypedDict):\n    prompt: str\n    response: str\n'
        'def echo(state):\n    return {"response": state["prompt"]}\n'
        'builder = StateGraph(State)\nbuilder.add_node("echo", echo)\n'
        'builder.add_edge(START, "echo")\nbuilder.add_edge("echo", END)\n'
        'graph = builder.compile()\n', encoding="utf-8"
    )
    requirement = root / "requirement.md"
    requirement.write_text("Echo the supplied prompt unchanged.", encoding="utf-8")
    return AgentRegistration(
        agent_id="test-echo", path=root, enabled=True, status="ready",
        framework="langgraph", source="test-fixture", requirement_path=requirement,
    )


@pytest.fixture(scope="session")
def enabled_agents(starter_agent: AgentRegistration) -> tuple[AgentRegistration, ...]:
    return tuple(
        replace(starter_agent, agent_id=f"test-echo-{index}", case_count=index)
        for index in range(1, 4)
    )


@pytest.fixture(scope="session")
def ready_agents(enabled_agents: tuple[AgentRegistration, ...]) -> tuple[AgentRegistration, ...]:
    return enabled_agents
