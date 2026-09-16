"""Saved execution provenance includes dynamically declared SDK distributions."""

from importlib.metadata import PackageNotFoundError
from types import SimpleNamespace

from agentbench.cli.sessions.configuration import installed_sdk_distributions


def test_distribution_names_come_from_selected_plugin_requirements(tmp_path, monkeypatch):
    from agentbench.sdk import discovery
    from agentbench.cli.sessions import configuration
    plugin = tmp_path / 'evaluation_plugin'
    plugin.mkdir()
    (plugin / 'requirements.txt').write_text(
        '# Deliberately different distribution and plugin names.\n'
        'other-evaluator[telemetry]==7.2\n'
        'Optional_Dependency>=1; python_version < "3.12"\n'
        '--extra-index-url https://example.invalid/simple\n')
    monkeypatch.setattr(discovery, 'SDK_ROOT', tmp_path)
    inspected = []
    def metadata(name):
        inspected.append(name)
        if name == 'other-evaluator':
            return '7.2'
        raise PackageNotFoundError(name)
    monkeypatch.setattr(configuration, 'version', metadata)
    result = installed_sdk_distributions(SimpleNamespace(name='evaluation_plugin'))
    assert result == {'optional-dependency': None, 'other-evaluator': '7.2'}
    assert inspected == ['other-evaluator', 'optional-dependency']


def test_host_sdk_distribution_upgrade_changes_provenance(tmp_path, monkeypatch):
    from agentbench.sdk import discovery
    from agentbench.cli.sessions import configuration
    from agentbench.harness.session.plan import digest_json
    plugin = tmp_path / 'plugin'
    plugin.mkdir()
    (plugin / 'requirements.txt').write_text('evaluator-package>=1\n')
    monkeypatch.setattr(discovery, 'SDK_ROOT', tmp_path)
    reference = SimpleNamespace(name='plugin')
    monkeypatch.setattr(configuration, 'version', lambda name: '1.0')
    previous = installed_sdk_distributions(reference)
    monkeypatch.setattr(configuration, 'version', lambda name: '2.0')
    assert digest_json(previous) != digest_json(installed_sdk_distributions(reference))
