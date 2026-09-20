"""ACP onboarding must use its own plan/schema and resume without graph files."""
import json
from types import SimpleNamespace
import pytest
from tests.agent_build_fixtures import source, plan, Client, build, FILES
from agentbench.onboarding.build_agent_env.frameworks.registry import strategy
from agentbench.onboarding.build_agent_env.planning.service import validate_plan
from agentbench.onboarding.build_agent_env.common.errors import BuildError
from agentbench.runtime.agentcontainer.config import tomllib
from agentbench.runtime.docker.adapter_build import stage_adapter_dependencies


def acp_plan(plan):
    return {**plan, 'framework': 'acp', 'bindings': []}


class ACPClient(Client):
    def generate(self, payload, *, prompt, schema):
        if payload.get('response_kind') == 'configuration_facts':
            self.requests.append(payload)
            assert 'ACP manifest' in prompt
            return {'status': 'complete', 'summary': 'Native stdio CLI', 'evidence': self.plan['evidence'],
                'missing_information': [], 'path': 'agent.toml', 'facts': {
                    'display_name': 'My Agent', 'framework': 'acp',
                    'adapter': {'command': ['node', '/opt/agent/agent/cli.js', 'acp'],
                                'cwd': '/home/agent/workspace', 'input_key': None,
                                'permission_policy': 'deny', 'auth_method': None},
                    'env_keys': [], 'secret_env_keys': [], 'models': [],
                    'tool_routes': [], 'input_fields': []}}
        return super().generate(payload, prompt=prompt, schema=schema)


def test_acp_generates_without_bindings_and_reuses_checkpoint(source, plan):
    plan = acp_plan(plan)
    files = {**FILES, 'Dockerfile': FILES['Dockerfile'].replace('COPY bindings/ ./bindings/\n', '')}
    client = ACPClient(plan, files=files)
    assert build(source, plan, client=client).status == 'generated'
    manifest = tomllib.loads((source.directory / 'agent.toml').read_text())
    assert manifest['adapter']['type'] == 'acp'
    assert manifest['adapter']['transport'] == 'stdio'
    assert 'mode' not in manifest['adapter'] and 'config' not in manifest['adapter']
    assert not (source.directory / 'bindings').exists()
    assert [p.get('target_path') for p in client.requests] == [None, 'agent.toml', 'Dockerfile', 'requirement.md']
    second = ACPClient(plan, files=files)
    assert build(source, plan, client=second).status == 'generated'
    assert second.requests == []


def test_acp_cannot_accept_a_langgraph_binding_plan(plan):
    bad = {**plan, 'framework': 'acp'}
    session = SimpleNamespace(environ={}, context={'files': [{'path': name} for name in plan['evidence']]})
    with pytest.raises(BuildError, match='schema'):
        validate_plan(bad, {}, session)


def test_adapter_overlay_is_registered_and_preserves_original_dockerfile(tmp_path):
    unit, stage = tmp_path / 'unit', tmp_path / 'stage'
    unit.mkdir(); stage.mkdir()
    (unit / 'agent.toml').write_text('framework="acp"\n')
    original = 'FROM python:3.12\nUSER agent\n'
    (unit / 'Dockerfile').write_text(original)
    dockerfile = stage / 'Dockerfile'; dockerfile.write_text(original)
    stage_adapter_dependencies(SimpleNamespace(agent_root=unit), stage, dockerfile)
    assert (stage / '.abb-adapter/requirements.txt').read_text() == 'agent-client-protocol==0.12.1\n'
    assert dockerfile.read_text().endswith('USER agent\n')
    assert 'python -m pip --isolated install' in dockerfile.read_text()
    assert (unit / 'Dockerfile').read_text() == original


def test_node_source_entrypoints_and_imports_are_collected_without_execution(tmp_path):
    from agentbench.onboarding.discovery import discover_files
    from agentbench.onboarding.source import DownloadedAgent
    from agentbench.onboarding.build_agent_env.openrouter_provider.context import collect_context
    from agentbench.onboarding.build_agent_env.openrouter_provider.settings import load_settings
    root = tmp_path / 'agent'; (root / 'src').mkdir(parents=True)
    (root / 'package.json').write_text('{"bin":{"example":"dist/main.js"}}')
    (root / 'src/main.ts').write_text('import {run} from "./server.js"; throw new Error("never execute");')
    (root / 'src/server.ts').write_text('export const run = "ACP stdio";')
    source = DownloadedAgent(tmp_path, 'https://github.com/example/cli', 'revision', discover_files(root))
    context = collect_context(source, load_settings(None), {})
    assert {'src/main.ts', 'src/server.ts'} <= {f['path'] for f in context['files']}
