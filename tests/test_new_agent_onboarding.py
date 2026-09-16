"""Offline lifecycle checks for the newly vendored Agent registrations."""

import hashlib
import json
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

import pytest

from agentbench.adapter.langgraph.config import LangGraphAdapterConfig
from agentbench.harness.registry import load_registry
from agentbench.runtime.agentcontainer.config import docker_structure
from agentbench.runtime.interception.config import InterceptionConfig


ROOT = Path(__file__).resolve().parents[1]
AGENTS = {
    'waku-agent': (
        '05-waku-agent', 'https://github.com/ShenSeanChen/waku-agent',
        'a2fb2563ebeacf65596a34e6a73cfedb040f8a1b'),
    'article-explainer': (
        '09-article-explainer', 'https://github.com/duartecaldascardoso/article-explainer',
        '2cf067dc4b9158b03361c7b3e2544e067b75f1ae'),
}


@pytest.mark.parametrize('agent_id', AGENTS)
def test_new_agent_is_registered_as_adapting_with_pinned_source(agent_id):
    unit, repository, revision = AGENTS[agent_id]
    registration = load_registry(ROOT / 'resources/registry.toml').find(agent_id)
    root = ROOT / 'resources/agents' / unit
    manifest = tomllib.loads((root / 'agent.toml').read_text())

    assert registration.enabled and registration.status == 'adapting'
    assert registration.path == root and registration.source == repository
    assert manifest['agent_id'] == agent_id
    assert manifest['source'] == {
        'repository': repository,
        'revision': revision,
        'downloaded_on': '2026-09-14',
        **({'license': manifest['source']['license']} if 'license' in manifest['source'] else {}),
    }
    assert (root / 'agent').is_dir() and not (root / 'agent/.git').exists()
    assert (root / 'agent/LICENSE').is_file() or (root / 'agent/LICENSE.md').is_file()
    assert (root / 'README.md').is_file() and (root / 'requirement.md').is_file()
    docker_structure(root, manifest)

    source = json.loads((root / 'source-manifest.json').read_text())
    assert source['repository'] == repository
    assert source['revision'] == revision
    assert source['local_additions'] == ['abb-langgraph.json']
    recorded = {item['path']: item for item in source['files']}
    actual = {
        path.relative_to(root / 'agent').as_posix()
        for path in (root / 'agent').rglob('*')
        if path.is_file()
        and '__pycache__' not in path.parts
        and path.suffix != '.pyc'
        and path.relative_to(root / 'agent').as_posix() not in source['local_additions']
    }
    assert set(recorded) == actual
    for name, item in recorded.items():
        content = (root / 'agent' / name).read_bytes()
        observed = (hashlib.sha256(content).hexdigest(), len(content))
        expected = {(item['sha256'], item['bytes'])}
        if 'lfs_sha256' in item:
            expected.add((item['lfs_sha256'], item['lfs_bytes']))
        assert observed in expected


@pytest.mark.parametrize('agent_id', AGENTS)
def test_new_agent_adapter_and_profile_are_valid_without_input_contract(tmp_path, agent_id):
    from kuma import create_run

    unit = AGENTS[agent_id][0]
    root = ROOT / 'resources/agents' / unit
    config = LangGraphAdapterConfig.from_agent_dir(root)
    assert config.binding and (root / 'bindings' / config.binding.split(':', 1)[0]).is_file()
    assert not (root / 'evaluation/input-contract.json').exists()

    seen = []
    def local_case(context):
        seen.append(context)
        return {'case_id': 'offline-onboarding', 'input_type': 'text',
                'inputs': [{'input_id': 'step-1', 'payload_type': 'text',
                            'payload': 'Offline profile validation'}]}

    repository = tmp_path / agent_id
    repository.mkdir()
    run = create_run(
        repo_path=repository,
        agent_profile_path=root / 'requirement.md',
        case_provider=local_case,
        judge=False,
        allow_local=True,
        track_files=False,
        max_steps=1,
    )
    try:
        assert run.case_id == 'offline-onboarding'
        assert seen[0].agent_profile_sections['behaviors_to_test'].strip()
    finally:
        run.cancel()


@pytest.mark.parametrize('agent_id', AGENTS)
def test_locally_executable_agent_has_valid_interception_declaration(agent_id):
    root = ROOT / 'resources/agents' / AGENTS[agent_id][0]
    interception = InterceptionConfig.from_agent_dir(root)
    assert interception is not None and interception.required
