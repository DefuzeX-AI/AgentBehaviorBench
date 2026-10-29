"""Historical execution targets keep commit identity separate from registration."""
from concurrent.futures import ThreadPoolExecutor
import json

import pytest

from agentbench.harness.registry import AgentRegistration, tomllib
from agentbench.evaluation.targets import prepare_target
from agentbench.trajectory.metadata import build_metadata, capture_target
from tests.test_runtime_source import unit, git


def registration(root):
    return AgentRegistration('test', root, True, 'ready', 'langgraph', 'test')


def test_two_commits_have_isolated_sources_and_reuse_verified_cache(unit, tmp_path):
    root, first, fetched = unit
    second = git(tmp_path / 'upstream', 'rev-parse', 'HEAD')
    original = (root / 'agent.toml').read_bytes()
    # Dirty default source must neither be copied nor changed.
    (root / 'agent').mkdir()
    (root / 'agent/app.py').write_text('local edits')
    reg = registration(root)
    cache = tmp_path / 'prepared'
    one = prepare_target(reg, first, cache_dir=cache)
    two = prepare_target(reg, second, cache_dir=cache)
    assert one.registration.path != two.registration.path
    assert (one.registration.path / 'agent/app.py').read_text() == 'version = 1\n'
    assert (two.registration.path / 'agent/app.py').read_text() == 'version = 2\n'
    assert (root / 'agent/app.py').read_text() == 'local edits'
    assert (root / 'agent.toml').read_bytes() == original
    assert prepare_target(reg, first, cache_dir=cache) == one
    assert fetched == [first, second]
    (root / 'Dockerfile').write_text('FROM python:3.13\nUSER agent\n')
    changed = prepare_target(reg, first, cache_dir=cache)
    assert changed.fingerprint != one.fingerprint
    assert fetched == [first, second]
    (one.registration.path / 'agent/app.py').write_text('tampered')
    with pytest.raises(ValueError, match='modified'):
        one.validate()


def test_install_uses_declared_source_recipe_and_not_current_package_lock(unit, tmp_path):
    root, first, _ = unit
    manifest = root / 'agent.toml'
    manifest.write_text(manifest.read_text().replace('method = "git"', 'method = "install"'))
    with pytest.raises(ValueError, match='Install Agent needs'):
        prepare_target(registration(root), first, cache_dir=tmp_path / 'prepared')
    manifest.write_text(manifest.read_text() + '\n[historical]\nstrategy="source"\ndockerfile="history/Dockerfile"\n')
    (root / 'history').mkdir()
    (root / 'history/Dockerfile').write_text('FROM python:3.12\nUSER agent\n')
    (root / 'install').mkdir()
    (root / 'install/package.json').write_text('{"version":"wrong"}')
    target = prepare_target(registration(root), first, cache_dir=tmp_path / 'prepared')
    path = target.registration.path
    actual = tomllib.loads((path / 'agent.toml').read_text())
    assert actual['source']['revision'] == first
    assert actual['source']['method'] == 'git'
    assert actual['build']['dockerfile'] == 'history/Dockerfile'
    assert not (path / 'agent/package.json').exists()
    assert not (path / 'install').exists()
    assert json.loads((path / 'provenance.json').read_text())['original_method'] == 'install'


def test_concurrent_preparation_publishes_one_target(unit, tmp_path):
    root, first, fetched = unit
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(prepare_target, registration(root), first, cache_dir=tmp_path / 'prepared')
                for _ in range(2)]
        a, b = [j.result() for j in jobs]
    assert a == b
    assert fetched == [first]


def test_failed_fetch_is_not_published(unit, tmp_path, monkeypatch):
    root, first, _ = unit
    def fail(*args, **kwargs):
        raise RuntimeError('offline')
    monkeypatch.setattr('agentbench.evaluation.targets.source_archive', fail)
    with pytest.raises(RuntimeError, match='offline'):
        prepare_target(registration(root), first, cache_dir=tmp_path / 'prepared')
    assert not [p for p in (tmp_path / 'prepared').iterdir() if p.is_dir()]


def test_trajectory_uses_frozen_target_even_when_default_manifest_changes(unit, tmp_path, monkeypatch):
    root, first, _ = unit
    frozen = capture_target(root)
    (root / 'agent.toml').write_text('source={revision="changed"}')
    class API:
        def read(self, name):
            return {'request/target.json': frozen, 'case.json': {'inputs': [{'payload': 'test'}]}}.get(name)
    monkeypatch.setattr('agentbench.trajectory.metadata._unit', lambda *a: pytest.fail('No registry lookup'))
    metadata, warnings = build_metadata(API(), agent_id='test', framework='langgraph',
                                        first_input={}, actors=[], project_root=tmp_path)
    assert metadata['system_architecture']['source_revision'] == first
    assert warnings == []
