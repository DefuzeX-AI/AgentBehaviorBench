"""Environment text survives the pinned SDK's Profile parsing and text budgets."""
import json

import pytest
from kuma.repository.agent_profiles import parse_agent_profile

from agentbench.runtime.contracts.environment import ExecutionEnvironment
from agentbench.sdk.common.artifacts import Artifacts
from agentbench.sdk.plugin.kuma.environment import generation_profile
from agentbench.sdk.plugin.kuma.environment import environment_text
from tests.test_kuma_requirement import REQUIREMENT


def test_intercepted_environment_distinguishes_local_and_external_transport():
    environment = ExecutionEnvironment(network={
        'mode': 'intercepted', 'other_egress': 'open', 'loopback': 'native_unobserved',
        'external_ipv6': 'blocked', 'external_non_dns_udp': 'blocked'})
    text = environment_text(environment)
    assert 'Loopback TCP/UDP communication is direct and unobserved' in text
    assert 'Other HTTP destinations: forwarded and recorded' in text
    assert 'External IPv6 is blocked' in text
    assert 'External non-DNS UDP is blocked' in text


@pytest.mark.parametrize('heading', ['Production Use Scenario', '生产使用场景'])
def test_profile_keeps_schema_references_and_original_behavior(tmp_path, heading):
    source = tmp_path / 'requirement.md'
    schema = tmp_path / 'input.json'
    schema.write_text('{"type":"object","properties":{"query":{"type":"string"}}}')
    text = REQUIREMENT.replace('Production Use Scenario', heading).replace(
        'input_type: text', 'input_type: structured\ninput_schema: input.json')
    source.write_text(text, encoding='utf-8')
    environment = ExecutionEnvironment(runtime='docker', workspace={
        'path': '/home/agent/workspace', 'initial_state': 'empty', 'fixture': None})
    files = Artifacts(tmp_path / 'output', environ={})
    with generation_profile(source, environment, files) as path:
        actual = parse_agent_profile(path)
        assert actual.input_schema == parse_agent_profile(source).input_schema
        assert actual.input_schema_path.is_relative_to(path.parent)
        assert '/home/agent/workspace' in actual.sections['production_scenario']
        assert 'initialized afresh' in actual.sections['production_scenario']
        assert actual.sections['behaviors_to_test'] == 'Return the supplied text unchanged.'
        assert actual.sections['prohibited_behaviors'] == 'Do not contact external services.'
        assert path.read_text(encoding='utf-8').count('Execution environment supplied by ABB') == 1
    assert not path.exists()
    assert source.read_text(encoding='utf-8') == text
    artifact = json.loads((files.directory / 'case-generation-profile.json').read_text(encoding='utf-8'))
    assert artifact['references']['references/input_schema.json']['type'] == 'object'
    with generation_profile(source, environment, files) as second:
        assert second.read_text(encoding='utf-8') == artifact['content']


def test_environment_does_not_silently_truncate_existing_behavior(tmp_path):
    source = tmp_path / 'requirement.md'
    source.write_text(REQUIREMENT.replace('Echo the current input.', 'x' * 3990))
    with pytest.raises(ValueError, match='text budget'):
        with generation_profile(source, ExecutionEnvironment(), Artifacts(tmp_path / 'out')):
            pytest.fail('Oversized Profile reached generation')


def test_profile_without_workspace_does_not_claim_one(tmp_path):
    source = tmp_path / 'requirement.md'
    source.write_text(REQUIREMENT)
    with generation_profile(source, ExecutionEnvironment(), Artifacts(tmp_path / 'out')) as path:
        text = parse_agent_profile(path).sections['production_scenario']
        assert 'No dedicated task workspace' in text
        assert '/home/agent/workspace' not in text


def test_tool_declaration_survives_profile_relocation(tmp_path):
    source = tmp_path / 'requirement.md'
    source.write_text(REQUIREMENT.replace('input_type: text',
                      'input_type: text\ntool_capabilities: tools.json'))
    tools = {'schema_version': 'kuma.agent_tool_capabilities.v1',
             'provenance': 'user_declared', 'tools': [{
                 'name': 'read_file', 'version': None, 'read_only': True,
                 'input_schema': {'type': 'object'}, 'side_effects': [],
                 'resource_scopes': [{'resource': 'workspace', 'access': 'read'}],
                 'evidence_types': ['tool_call']}]}
    (tmp_path / 'tools.json').write_text(json.dumps(tools))
    with generation_profile(source, ExecutionEnvironment(), Artifacts(tmp_path / 'out')) as path:
        actual = parse_agent_profile(path)
        assert actual.tool_capabilities.to_dict() == parse_agent_profile(source).tool_capabilities.to_dict()
        assert actual.tool_capabilities_path.is_relative_to(path.parent)
