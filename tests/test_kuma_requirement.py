"""The registered requirement is the exact document used for KUMA generation."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentbench.harness.errors import ProviderSelectionError
from agentbench.harness.registry import load_registry
from agentbench.runtime.agentcontainer.config import tomllib
from agentbench.sdk.plugin.kuma.benchmark import KumaContainerRunner
from agentbench.sdk.plugin.kuma.image import evaluation_agent
from agentbench.sdk.plugin.kuma.worker import execute


ROOT = Path(__file__).resolve().parents[1]
REQUIREMENT = """---
agent_description: Requirement document controls this Agent's evaluation.
input_type: text
---
## Production Use Scenario
Echo the current input.
## Behaviors to Test
Return the supplied text unchanged.
## Known Limitations or Prohibited Behaviors
Do not contact external services.
"""


@pytest.fixture
def unit(tmp_path):
    root = tmp_path / 'unit'
    (root / 'agent').mkdir(parents=True)
    (root / 'requirement.md').write_text(REQUIREMENT)
    (root / 'agent.toml').write_text(
        'agent_id = "requirement-test"\nframework = "fixture"\n'
        '[runtime]\ntype = "docker"\n'
        '[launch]\nargv = ["python", "agent.py"]\n')
    (root / 'Dockerfile').write_text('FROM python:3.11-slim\nUSER agent\n')
    return root


@pytest.mark.parametrize('step_options', [{}, {'max_steps': None}, {'max_steps': 1}])
def test_worker_passes_requirement_contents_to_real_sdk(unit, tmp_path, monkeypatch, step_options):
    import kuma

    create_run = kuma.create_run
    observed = []

    def cases(context):
        observed.append(context)
        return {'case_id': 'requirement-case', 'input_type': 'text', 'inputs': [
            {'input_id': 'one', 'payload_type': 'text', 'payload': 'echo this'}]}

    def offline_create(**options):
        assert options['agent_profile_path'] == unit / 'requirement.md'
        assert options['allow_local'] is False
        if step_options.get('max_steps') is None:
            assert 'max_steps' not in options
        else:
            assert options['max_steps'] == step_options['max_steps']
        # Exercise real SDK parsing on the host without changing production's
        # container requirement or invoking either official remote Provider.
        options['allow_local'] = True
        # The SDK requires an explicit limit for this custom offline Provider.
        # The assertions above check the unmodified production call first.
        options.setdefault('max_steps', 1)
        return create_run(**options, case_provider=cases,
                          judge_provider=lambda context: {'status': 'pass', 'issues': []})

    monkeypatch.setattr(kuma, 'create_run', offline_create)
    monkeypatch.setenv('KUMA_API_KEY', 'offline-not-sent')
    output = tmp_path / 'output'
    code = asyncio.run(execute(unit, output, {'mode': 'generate', 'count': 1, **step_options}))
    error = output / 'error.json'
    assert code == 0, error.read_text() if error.exists() else 'generation failed'
    assert len(observed) == 1
    assert observed[0].agent_description == 'Requirement document controls this Agent\'s evaluation.'
    assert observed[0].agent_profile_sections['behaviors_to_test'] == 'Return the supplied text unchanged.'
    collection = json.loads((output / 'case-collection.json').read_text())
    assert collection['cases'][0]['case_id'] == 'requirement-case'


def test_legacy_profile_does_not_replace_a_missing_requirement(unit):
    (unit / 'evaluation').mkdir()
    (unit / 'requirement.md').rename(unit / 'evaluation/profile.md')
    runner = KumaContainerRunner(environ={'KUMA_API_KEY': 'offline-not-sent'})
    with pytest.raises(ProviderSelectionError, match='requirement.md'):
        runner.validate_sdk(SimpleNamespace(path=unit))


def test_evaluation_image_copies_the_same_requirement(unit):
    agent = SimpleNamespace(path=unit, agent_id='requirement-test', framework='fixture')
    with evaluation_agent(agent) as staged:
        assert (staged.path / 'requirement.md').read_text() == REQUIREMENT
        dockerfile = (staged.path / 'Dockerfile').read_text()
        assert 'COPY requirement.md /opt/agent/requirement.md' in dockerfile
        assert 'COPY evaluation/' not in dockerfile
        assert not (staged.path / 'evaluation').exists()


def test_optional_schema_is_preserved_in_evaluation_image(unit):
    from kuma.repository.agent_profiles import parse_agent_profile

    (unit / 'evaluation').mkdir()
    schema = '{"type":"object","properties":{"topic":{"type":"string"}},"required":["topic"]}'
    (unit / 'evaluation/input-schema.json').write_text(schema)
    (unit / 'requirement.md').write_text(REQUIREMENT.replace(
        'input_type: text', 'input_type: structured\ninput_schema: evaluation/input-schema.json'))
    agent = SimpleNamespace(path=unit, agent_id='requirement-test', framework='fixture')
    with evaluation_agent(agent) as staged:
        assert 'COPY evaluation/ /opt/agent/evaluation/' in (staged.path / 'Dockerfile').read_text()
        assert (staged.path / 'evaluation/input-schema.json').read_text() == schema
        assert parse_agent_profile(staged.path / 'requirement.md').input_type == 'structured'


def test_every_registered_requirement_is_a_valid_sdk_profile():
    from kuma.repository.agent_profiles import parse_agent_profile

    registry = load_registry(ROOT / 'resources/registry.toml')
    units = sorted((ROOT / 'resources/agents').glob('*/agent.toml'))
    assert units
    for manifest in units:
        unit = manifest.parent
        profile = parse_agent_profile(unit / 'requirement.md')
        registration = registry.find(tomllib.loads(manifest.read_text())['agent_id'], enabled_only=False)
        assert registration.requirement_path == profile.path
        assert not (unit / 'evaluation/profile.md').exists()
