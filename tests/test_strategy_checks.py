from pathlib import Path
from types import SimpleNamespace
import json
from agentbench.sdk.contracts import SDKStrategyChecks
from agentbench.sdk.plugin.kuma.plugin import plugin
from agentbench.sdk.plugin.kuma.strategy_checks import KumaStrategyChecker
from agentbench.sdk.strategy_checks import check_agents, snapshot_path, StrategyChecks
from agentbench.cli.terminal_ui.presentation import print_agents

CATALOG = {'catalog_release': 'test-release', 'groups': [
    {'id': 'research', 'version': '1', 'display_name': 'Research', 'available': True},
    {'id': 'disabled', 'version': '1', 'display_name': 'Disabled', 'available': False}]}


def test_kuma_strategy_contract_and_exact_version():
    assert isinstance(plugin, SDKStrategyChecks)
    checker = KumaStrategyChecker(CATALOG)
    assert checker.strategies_check('research').status == 'valid'
    assert checker.strategies_check('research', '2').status == 'invalid'
    assert checker.strategies_check('missing', '1').status == 'invalid'
    assert checker.strategies_check('disabled', '1').status == 'invalid'


def agents(tmp_path):
    result = []
    for name in ('one', 'two'):
        path = tmp_path / name
        path.mkdir()
        (path/'requirement.md').write_text('profile')
        result.append(SimpleNamespace(agent_id=name, path=path, framework='test', status='ready', case_count=1))
    return result


class FakeSDK:
    calls = 0
    def strategy_selection(self, directory):
        return ('research', '1')
    def strategy_checker(self, **kwargs):
        self.calls += 1
        return KumaStrategyChecker(CATALOG)


def test_catalog_fetched_once_and_public_snapshot_saved(tmp_path):
    sdk = FakeSDK()
    selected = agents(tmp_path)
    result = check_agents(selected, sdk=sdk, root=tmp_path, environ={})
    assert sdk.calls == 1
    assert all(r['status'] == 'valid' for r in result.values())
    saved = json.loads(snapshot_path(tmp_path, selected[0].path).read_text())
    assert saved['catalog_release'] == 'test-release'
    assert saved['checked_at'] and saved['profile_sha256']


def test_connection_failure_is_not_invalid_and_no_secret_leaks(tmp_path):
    class Offline(FakeSDK):
        def strategy_checker(self, **kwargs):
            raise RuntimeError('secret-from-provider')
    result = check_agents(agents(tmp_path), sdk=Offline(), root=tmp_path, environ={})
    assert all(r['status'] == 'unverified' for r in result.values())
    assert 'secret-from-provider' not in str(result)


def test_invalid_profile_and_unsupported_sdk(tmp_path):
    class Invalid(FakeSDK):
        def strategy_selection(self, directory):
            raise ValueError('bad yaml')
    selected = agents(tmp_path)
    assert check_agents(selected, sdk=Invalid(), root=tmp_path)['one']['status'] == 'invalid'
    assert check_agents(selected, sdk=object(), root=tmp_path)['one']['status'] == 'unsupported'


def test_discovery_shows_red_invalid_below_framework(tmp_path, monkeypatch):
    from agentbench.cli.terminal_ui import presentation
    monkeypatch.setattr(presentation.time, 'sleep', lambda _: None)
    lines = []
    print_agents(agents(tmp_path)[:1], lines.append, {'one': {'status': 'invalid', 'id': 'missing', 'version': '1'}})
    output = '\n'.join(lines)
    assert '(strategy invalid)' in output
    assert '\x1b[31m' in output
    assert output.index('framework:') < output.index('strategy:') < output.index('path:')


def test_discovery_sdk_version_stays_inside_panel(monkeypatch):
    from agentbench.cli.terminal_ui import presentation
    monkeypatch.setattr(presentation.time, 'sleep', lambda _: None)
    checks = StrategyChecks()
    for latest in (None, '0.3.1'):
        checks.sdk_info = {'name': 'KUMA', 'version': '0.2.7', 'latest_version': latest}
        lines = []
        print_agents((), lines.append, checks)
        line = next(line for line in lines if 'sdk:' in line)
        plain = presentation.ANSI_PATTERN.sub('', line)
        assert 'sdk: KUMA 0.2.7' in plain
        assert ('(Update available: 0.3.1)' in plain) == bool(latest)
        assert plain.startswith('|') and plain.endswith('|')
        assert 'https://' not in plain


def test_kuma_explicit_version_check_prevents_background_reminder(monkeypatch, capsys):
    import kuma.updates as updates
    monkeypatch.delenv('KUMA_DISABLE_UPDATE_CHECK', raising=False)
    monkeypatch.setattr(updates, '_cached', None)
    monkeypatch.setattr(updates, '_expires', 0)
    monkeypatch.setattr(updates, '_inflight', False)
    monkeypatch.setattr(updates, '_fetch_release', lambda: {
        'status': 'required', 'current_version': '0.2.7', 'latest_version': '0.3.1'})
    threads = []
    monkeypatch.setattr(updates.threading, 'Thread', lambda **kwargs: threads.append(kwargs))
    assert plugin.version_info() == {'name': 'KUMA', 'version': '0.2.7', 'latest_version': '0.3.1'}
    updates.schedule_update_check()
    assert threads == []
    assert capsys.readouterr().err == ''


def test_local_discovery_preserves_declaration_without_network(tmp_path, monkeypatch):
    from agentbench.sdk.plugin.local.plugin import plugin as local
    from agentbench.cli.terminal_ui import presentation
    import socket
    def no_network(*args, **kwargs):
        raise AssertionError('Local discovery must not access the network')
    monkeypatch.setattr(socket.socket, 'connect', no_network)
    monkeypatch.setattr(presentation.time, 'sleep', lambda _: None)
    selected = agents(tmp_path)[:1]
    (selected[0].path / 'requirement.md').write_text(
        '---\nstrategy_group:\n  schema_version: kuma.strategy_group_selection.v1\n'
        '  id: basic-safety-cli\n  version: "1"\n'
        'agent_description: A folder moving agent.\ninput_type: text\n---\n'
        '## Production Use Scenario\nMove a folder.\n'
        '## Behaviors to Test\nMove the requested folder.\n'
        '## Known Limitations or Prohibited Behaviors\nDo not delete other files.\n', encoding='utf-8')
    checks = check_agents(selected, sdk=local, environ={}, root=tmp_path)
    assert checks.sdk_info == {'name': 'local', 'version': '0.0.1', 'latest_version': None}
    assert checks['one']['id'] == 'basic-safety-cli'
    assert checks['one']['version'] == '1'
    assert checks['one']['status'] == 'unverified'
    lines = []
    print_agents(selected, lines.append, checks)
    output = '\n'.join(lines)
    assert 'sdk: local 0.0.1' in output
    assert 'basic-safety-cli@1 (strategy unverified)' in output
    assert 'not declared' not in output
