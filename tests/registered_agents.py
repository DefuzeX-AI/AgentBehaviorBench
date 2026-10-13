"""Resolve bundled test subjects by stable registry identity, not folder numbers."""
import importlib.util
from functools import lru_cache
from pathlib import Path

import pytest

from agentbench.harness.registry import load_registry, tomllib

ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def registrations():
    path = ROOT / 'resources/registry.toml'
    registry = load_registry(path)
    with path.open('rb') as stream:
        identities = tomllib.load(stream)['agents']
    return tuple(registry.find(row['agent_id'], enabled_only=False) for row in identities)


def unit(agent_id):
    matches = [agent for agent in registrations() if agent.agent_id == agent_id]
    assert len(matches) == 1, f'Expected one registered Agent: {agent_id}'
    path = matches[0].path
    assert (path / 'agent.toml').is_file(), f'Missing registered unit: {path}'
    return path


def binding(agent_id):
    path = unit(agent_id)
    with (path / 'agent.toml').open('rb') as stream:
        manifest = tomllib.load(stream)
    filename, _, factory = manifest['adapter']['binding'].rpartition(':')
    spec = importlib.util.spec_from_file_location('test_binding_' + agent_id.replace('-', '_'),
                                                  path / 'bindings' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(getattr(module, factory))
    return module


def require_source(agent_id, relative):
    source = unit(agent_id) / 'agent'
    if not source.is_dir():
        pytest.skip(f'{agent_id}: acquire the pinned ignored agent/ source before this integration test')
    path = source / relative
    assert path.is_file(), f'Incomplete native source: {path}'
    return path
