"""Issue #429: ZeroClaw must be pinned to a release that lets an approved shell call rerun.

v0.8.5 aborted the turn (and the ACP session) when an approved shell command was
requested again with identical arguments in the same turn. The fix
(zeroclaw-labs/zeroclaw#11653) first shipped in v0.8.6.
"""
import importlib.util
import json

from agentbench.runtime.agentcontainer.config import tomllib
from tests.registered_agents import unit

V086_COMMIT = 'c473221313341a853e04122f93bb9bd26b5e6c47'


def _distribution():
    return json.loads((unit('zeroclaw') / 'install' / 'distribution.json').read_text(encoding='utf-8'))


def test_release_pin_includes_the_approved_rerun_fix():
    dist = _distribution()
    version = tuple(int(part) for part in dist['version'].split('.'))
    assert version >= (0, 8, 6)
    assert dist['tag'] == 'v' + dist['version']
    assert f"/releases/download/{dist['tag']}/" in dist['url']
    assert len(dist['sha256']) == 64 and set(dist['sha256']) <= set('0123456789abcdef')


def test_provenance_records_the_installed_release_commit():
    root = unit('zeroclaw')
    dist = _distribution()
    manifest = tomllib.loads((root / 'agent.toml').read_text(encoding='utf-8'))
    provenance = json.loads((root / 'source-manifest.json').read_text(encoding='utf-8'))
    assert dist['commit'] == V086_COMMIT
    assert manifest['source']['revision'] == dist['commit']
    assert provenance['revision'] == dist['commit']


def test_launcher_keeps_the_browser_automation_tool_on_v086():
    path = unit('zeroclaw') / 'bootstrap' / 'launch.py'
    spec = importlib.util.spec_from_file_location('zeroclaw_issue429_launch', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    config = tomllib.loads(module.config_toml('https://models.example/v1', 'model-x'))
    assert config['browser']['enabled'] is True
    assert config['browser']['automation_enabled'] is True
    assert config['browser']['backend'] == 'agent_browser'
