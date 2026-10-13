"""Onboarding must retain integration inputs outside ignored source."""
from dataclasses import replace
from types import SimpleNamespace
import json

import pytest

from agentbench.onboarding.build_agent_env.build_toml.provenance import source_metadata
from agentbench.onboarding.build_agent_env.build_toml.validation import validate_manifest
from agentbench.onboarding.build_agent_env.common.errors import BuildError
from agentbench.onboarding.build_agent_env.common.validation import validate_unit
from agentbench.sdk.plugin.kuma.plugin import plugin
from tests.agent_build_fixtures import source, plan, Client, FILES, MANIFEST, build, write


@pytest.fixture(autouse=True)
def isolated_source_cache(tmp_path, monkeypatch):
    monkeypatch.setattr('agentbench.project.project_root', lambda: tmp_path)


def descriptor(source):
    return (source.directory/'agent/langgraph.json').read_text()


def test_add_copies_install_before_generation_and_repairs_before_final_validation(source, plan):
    write(source.directory, 'install/abb-langgraph.json', descriptor(source))
    files = {**FILES, 'agent.toml': MANIFEST.replace('langgraph.json', 'abb-langgraph.json')}
    client = Client(plan, files=files)
    assert build(source, plan, client=client).status == 'generated'
    assert 'abb-langgraph.json' in {item['path'] for item in client.requests[0]['context']['files']}
    generated = source.directory/'agent/abb-langgraph.json'
    generated.unlink()
    assert validate_unit(source.directory, plugin) == 'my-agent'
    assert generated.read_bytes() == (source.directory/'install/abb-langgraph.json').read_bytes()


def test_abb_descriptor_only_in_ignored_source_cannot_register(source, plan):
    write(source.directory, 'agent/abb-langgraph.json', descriptor(source))
    files = {**FILES, 'agent.toml': MANIFEST.replace('langgraph.json', 'abb-langgraph.json')}
    with pytest.raises(BuildError, match='outer install/'):
        build(source, plan, client=Client(plan, files=files))
    assert not (source.directory.parents[1]/'registry.toml').exists()


def test_install_conflict_stops_before_model_request(source, plan):
    write(source.directory, 'install/langgraph.json', '{}')
    client = Client(plan)
    with pytest.raises(BuildError, match='modified'):
        build(source, plan, client=client)
    assert not client.requests
    assert 'graphs' in descriptor(source)


def test_manifest_rejects_different_durable_descriptor(source, plan):
    write(source.directory, 'install/langgraph.json', '{}')
    with pytest.raises(BuildError, match='differs from install/'):
        validate_manifest(MANIFEST, SimpleNamespace(source=source, agent_id=None, plan=plan))


def test_package_unit_without_install_cannot_register(source, plan):
    assert build(source, plan).status == 'generated'
    path = source.directory/'agent.toml'
    path.write_text(path.read_text().replace('method = "bundled"', 'method = "install"'))
    with pytest.raises(BuildError, match='installation directory'):
        validate_unit(source.directory, plugin)


def pinned(source):
    source = replace(source, revision='a'*40)
    write(source.directory, 'source-manifest.json', json.dumps(dict(repository=source.repository, revision=source.revision)))
    return source


def test_new_github_import_automatically_uses_pinned_git(source):
    assert source_metadata(pinned(source))['method'] == 'git'


@pytest.mark.parametrize('unsupported', ['local', 'submodules', 'lfs', 'warnings'])
def test_manual_source_requirements_remain_bundled(source, unsupported):
    source = pinned(source)
    if unsupported == 'local':
        source = replace(source, source_type='local-directory')
    elif unsupported == 'submodules':
        write(source.directory, 'agent/.gitmodules', '[submodule "dependency"]')
    elif unsupported == 'lfs':
        write(source.directory, 'agent/.gitattributes', '*.bin filter=lfs diff=lfs merge=lfs -text')
    else:
        source = replace(source, warnings=('manual source required',))
    assert source_metadata(source)['method'] == 'bundled'


@pytest.mark.parametrize('method', ['bundled', 'install', 'git'])
def test_existing_explicit_acquisition_policy_is_preserved(source, method):
    source = pinned(source)
    write(source.directory, 'agent.toml', '[source]\nmethod="'+method+'"\nrepository="'+source.repository+'"\nrevision="'+source.revision+'"\n')
    assert source_metadata(source)['method'] == method


def test_existing_install_unit_requires_inputs_before_generation(source, plan):
    write(source.directory, 'agent.toml', MANIFEST + '\n[source]\nmethod="install"\n')
    client = Client(plan)
    with pytest.raises(BuildError, match='installation directory'):
        build(source, plan, client=client)
    assert not client.requests
