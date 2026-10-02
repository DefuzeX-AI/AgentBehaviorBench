"""Human reference observations must not change or leak into Agent execution."""

from types import SimpleNamespace

import pytest

from agentbench.harness.session.plan import source_digest
from agentbench.runtime.docker.worker_build import worker_build_context
from agentbench.sdk.plugin.kuma.image import evaluation_agent


@pytest.fixture
def unit(tmp_path):
    root = tmp_path / 'unit'
    (root / 'agent/ground_truth').mkdir(parents=True)
    (root / 'agent/ground_truth/native.txt').write_text('Upstream Agent source data')
    (root / 'agent.toml').write_text(
        'agent_id = "example"\nframework = "langgraph"\n'
        '[runtime]\ntype = "docker"\n'
        '[launch]\nargv = ["python", "native.py"]\n')
    (root / 'requirement.md').write_text('Agent profile')
    (root / 'Dockerfile').write_text('FROM python:3.13-slim\nCOPY . /opt/agent/\nUSER agent\n')
    return root


def add_reference(root):
    reference = root / 'ground_truth/defect-1/observation.json'
    reference.parent.mkdir(parents=True)
    reference.write_text('{"confirmed_defect":"private evaluation answer"}')
    return reference


def test_reference_observations_do_not_change_source_digest_but_native_source_does(unit):
    original = source_digest(unit)
    reference = add_reference(unit)
    assert source_digest(unit) == original
    reference.write_text('{"confirmed_defect":"additional human observation"}')
    assert source_digest(unit) == original
    (unit / 'agent/ground_truth/native.txt').write_text('Changed upstream source data')
    assert source_digest(unit) != original


@pytest.mark.parametrize('nested_context', [False, True])
def test_worker_build_excludes_unit_references_and_preserves_native_source(unit, nested_context):
    reference = add_reference(unit)
    context_root = unit / 'agent' if nested_context else unit
    dockerfile = context_root / 'Dockerfile'
    if nested_context:
        dockerfile.write_bytes((unit / 'Dockerfile').read_bytes())
    config = SimpleNamespace(agent_root=unit, build_context=context_root, dockerfile=dockerfile)
    original = dockerfile.read_bytes()
    with worker_build_context(config) as (context, staged_dockerfile):
        native = context / ('ground_truth' if nested_context else 'agent/ground_truth') / 'native.txt'
        assert native.read_text() == 'Upstream Agent source data'
        assert not (context / 'ground_truth/defect-1/observation.json').exists()
        assert not list(context.rglob('observation.json'))
        assert 'COPY . /opt/agent/' in staged_dockerfile.read_text()
    assert reference.is_file()
    assert dockerfile.read_bytes() == original


def test_reference_directory_cannot_be_selected_as_worker_build_context(unit):
    reference = add_reference(unit)
    config = SimpleNamespace(agent_root=unit, build_context=reference.parent,
                             dockerfile=unit / 'Dockerfile')
    with pytest.raises(ValueError, match='Ground truth cannot be an Agent build context'):
        with worker_build_context(config):
            pytest.fail('Reference directory was exposed as an execution context')


def test_sdk_overlay_excludes_unit_references_and_preserves_native_source(unit):
    reference = add_reference(unit)
    agent = SimpleNamespace(path=unit, agent_id='example', framework='langgraph')
    original = (unit / 'Dockerfile').read_bytes()
    with evaluation_agent(agent, backend=None) as staged:
        assert not (staged.path / 'ground_truth').exists()
        assert (staged.path / 'agent/ground_truth/native.txt').read_text() == 'Upstream Agent source data'
        assert (staged.path / 'requirement.md').read_text() == 'Agent profile'
    assert reference.is_file()
    assert (unit / 'Dockerfile').read_bytes() == original
