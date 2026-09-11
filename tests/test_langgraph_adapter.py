from pathlib import Path
from uuid import uuid4

import pytest

from agentbench.harness import AgentRegistration

from agentbench.adapter.langgraph import LangGraphAdapter, LangGraphAdapterConfig
from agentbench.adapter.langgraph.config import LangGraphConfigurationError
from agentbench.adapter.langgraph.loader import LangGraphLoadError


def test_config_resolves_langgraph_entrypoint(starter_agent: AgentRegistration) -> None:
    """Check adapter config reads langgraph.json."""
    agent_root = starter_agent.path
    config = LangGraphAdapterConfig.from_agent_dir(agent_root)

    assert config.graph_id == "agent"
    assert config.entrypoint == "./graph.py:graph"
    assert config.input_key == "prompt"
    assert config.output_key == "response"
    assert config.agent_root == agent_root
    assert config.source_root == agent_root / "agent"


def test_adapter_loads_and_invokes_graph(starter_agent: AgentRegistration) -> None:
    """Check adapter can run the starter graph."""
    agent_root = starter_agent.path
    adapter = LangGraphAdapter.from_agent_dir(agent_root)

    invocation = adapter.invoke("DEFUZEX_AGENT_READY")

    assert adapter.is_loaded
    assert invocation.output == "DEFUZEX_AGENT_READY"
    assert invocation.raw_output == {
        "prompt": "DEFUZEX_AGENT_READY",
        "response": "DEFUZEX_AGENT_READY",
    }


@pytest.mark.parametrize("layout", ["", "src"])
def test_nested_source_imports_its_own_package(tmp_path: Path, layout: str) -> None:
    """Outer metadata wins; both upstream root and src packages remain importable."""
    source = tmp_path / "agent"
    package_name = f"layout_graph_{uuid4().hex}"
    package = source / layout / package_name
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "helper.py").write_text(
        "class Graph:\n"
        "    def invoke(self, input, **kwargs):\n"
        "        return {'response': input['prompt']}\n",
        encoding="utf-8",
    )
    (package / "graph.py").write_text(
        "from .helper import Graph\ngraph = Graph()\n", encoding="utf-8"
    )
    entry = (Path(layout) / package_name / "graph.py").as_posix()
    (source / "langgraph.json").write_text(
        '{"graphs": {"agent": "' + entry + ':graph"}}', encoding="utf-8"
    )
    (tmp_path / "agent.toml").write_text(
        '[adapter]\ntype="langgraph"\nconfig="langgraph.json"\n'
        'graph_id="agent"\ninput_key="prompt"\noutput_key="response"\n',
        encoding="utf-8",
    )
    (source / "agent.toml").write_text("invalid upstream manifest", encoding="utf-8")
    (tmp_path / "langgraph.json").write_text("invalid outer config", encoding="utf-8")

    adapter = LangGraphAdapter.from_agent_dir(tmp_path)
    assert adapter.invoke("nested source works").output == "nested source works"


@pytest.mark.parametrize("escape", ["config", "entrypoint"])
def test_source_paths_cannot_escape_to_outer_unit(tmp_path: Path, escape: str) -> None:
    source = tmp_path / "agent"
    source.mkdir()
    config_name = "../langgraph.json" if escape == "config" else "langgraph.json"
    (tmp_path / "agent.toml").write_text(
        '[adapter]\ntype="langgraph"\ngraph_id="agent"\n'
        f'config="{config_name}"\n', encoding="utf-8"
    )
    for root in (tmp_path, source):
        (root / "langgraph.json").write_text(
            '{"graphs": {"agent": "../graph.py:graph"}}', encoding="utf-8"
        )
    (tmp_path / "graph.py").write_text("raise AssertionError('outer source loaded')")

    expected = LangGraphConfigurationError if escape == "config" else LangGraphLoadError
    with pytest.raises(expected, match="escapes agent directory"):
        LangGraphAdapter.from_agent_dir(tmp_path).invoke("test")
