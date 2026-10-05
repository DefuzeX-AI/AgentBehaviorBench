"""A Python LangGraph factory does not need an upstream graph JSON descriptor."""
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from agentbench.adapter.langgraph.config import LangGraphAdapterConfig, LangGraphConfigurationError
from agentbench.onboarding.build_agent_env.build_toml.validation import validate_manifest
from agentbench.onboarding.build_agent_env.common.errors import BuildError
from tests.agent_build_fixtures import source, plan, Client, FILES, MANIFEST, build


def without_descriptor(manifest):
    return ''.join(line for line in manifest.splitlines(keepends=True)
                   if not line.startswith(('config =', 'graph_id =')))


def test_native_factory_builds_resumes_and_invokes_without_source_json(source, plan):
    descriptor = source.directory / 'agent/langgraph.json'
    descriptor.unlink()
    native = '''from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
class State(TypedDict):
    message: str
    answer: str
def build_graph():
    builder = StateGraph(State)
    builder.add_node("respond", lambda state: {"answer": state["message"].upper()})
    builder.add_edge(START, "respond")
    builder.add_edge("respond", END)
    return builder.compile()
'''
    native_path = source.directory / 'agent/src/pkg/graph.py'
    native_path.write_text(native, encoding='utf-8')
    original = {path.relative_to(source.directory / 'agent'): path.read_bytes()
                for path in (source.directory / 'agent').rglob('*') if path.is_file()}
    files = {**FILES, 'agent.toml': without_descriptor(MANIFEST),
             'bindings/bridge.py': 'def create_graph():\n    from pkg.graph import build_graph\n    return build_graph()\n'}
    assert build(source, plan, client=Client(plan, files=files)).status == 'generated'
    config = LangGraphAdapterConfig.from_agent_dir(source.directory)
    assert config.binding == config.entrypoint == 'bridge.py:create_graph'
    assert config.graph_id is None
    resumed = Client(plan, files=files)
    assert build(source, plan, client=resumed).status == 'generated'
    assert resumed.requests == []
    assert original == {path.relative_to(source.directory / 'agent'): path.read_bytes()
                        for path in (source.directory / 'agent').rglob('*') if path.is_file()}
    script = '''import sys
from agentbench.adapter.langgraph.adapter import LangGraphAdapter
adapter = LangGraphAdapter.from_agent_dir(sys.argv[1])
assert adapter.invoke("native factory").output["answer"] == "NATIVE FACTORY"
adapter.close()
'''
    result = subprocess.run([sys.executable, '-B', '-c', script, str(source.directory)],
                            env={**os.environ, 'PYTHONPATH': str(source.directory / 'agent/src')},
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_native_factory_does_not_hide_an_explicit_missing_descriptor(source, plan):
    session = SimpleNamespace(source=source, agent_id=None, plan=plan)
    with pytest.raises(BuildError, match='existing file inside agent'):
        validate_manifest(MANIFEST.replace('langgraph.json', 'missing.json'), session)


def test_graph_id_cannot_be_invented_without_descriptor(source, plan):
    session = SimpleNamespace(source=source, agent_id=None, plan=plan)
    with pytest.raises(BuildError, match='graph_id requires'):
        validate_manifest(without_descriptor(MANIFEST) + 'graph_id = "invented"\n', session)


def test_runtime_without_binding_or_descriptor_reports_required_interface(source):
    content = without_descriptor(MANIFEST).replace('binding = "bridge.py:create_graph"\n', '')
    (source.directory / 'agent.toml').write_text(content, encoding='utf-8')
    with pytest.raises(LangGraphConfigurationError, match='config.*binding'):
        LangGraphAdapterConfig.from_agent_dir(source.directory)


def test_real_add_cli_imports_native_factory_generates_files_and_reuses_them(source, plan, monkeypatch, capsys):
    from agentbench.cli.main import cli
    from agentbench.onboarding import workflow
    from agentbench.onboarding.build_agent_env import service

    upstream = source.directory / 'agent'
    (upstream / 'langgraph.json').unlink()
    (upstream / 'pyproject.toml').write_text(
        '[project]\nname="native-agent"\n[project.scripts]\nnative="pkg.cli:app"\n', encoding='utf-8')
    (upstream / 'src/pkg/cli.py').write_text('from pkg.graph import graph\n', encoding='utf-8')
    files = {**FILES, 'agent.toml': without_descriptor(MANIFEST)}
    client = Client(plan, files=files)
    monkeypatch.setattr(workflow, 'load_project_environment', lambda *args: None)
    monkeypatch.setattr(service, 'OpenRouterClient', lambda *args, **kwargs: client)
    arguments = ['agent', 'add', str(upstream), '-b', '--no-view',
                 '--agents-dir', str(source.directory.parent),
                 '--registry', str(source.directory.parents[1] / 'registry.toml')]
    assert cli(arguments) == 0
    assert 'static checks passed, certification pending' in capsys.readouterr().err
    request_count = len(client.requests)
    assert request_count > 0
    assert cli(arguments) == 0
    assert len(client.requests) == request_count
