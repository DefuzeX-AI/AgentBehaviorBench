"""Issue #19: registry failures are handled before any paid execution."""
from agentbench.cli.features import run
from agentbench.cli.features.certify import certify
from agentbench.cli.main import cli


def test_run_handles_missing_registry(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(run, 'DEFAULT_REGISTRY_PATH', tmp_path/'missing.toml')
    monkeypatch.setattr(run, 'LOGO_PAUSE_SECONDS', 0)
    assert cli(['run', '--yes', '--no-view']) == 2
    assert 'Configuration error' in capsys.readouterr().out


def test_certify_handles_missing_registry(tmp_path):
    output = []
    assert certify('agent', registry_path=tmp_path/'missing.toml', output_fn=output.append) == 2
    assert any('Certification error' in line for line in output)
