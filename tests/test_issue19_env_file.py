"""Issue #19: an unreadable env-file is a configuration error for every command, not a traceback."""
import pytest

from agentbench.cli import environment
from agentbench.cli.features import run
from agentbench.cli.main import cli


@pytest.fixture
def unreadable_env(tmp_path, monkeypatch):
    path = tmp_path / 'locked.env'
    path.write_text('OPENROUTER_MODEL=test\n')

    def load_dotenv(selected, override=False):
        raise PermissionError(13, 'Permission denied', str(selected))

    monkeypatch.setattr(environment, 'load_dotenv', load_dotenv)
    return path


def test_loader_reports_the_file_and_the_reason(unreadable_env):
    with pytest.raises(environment.EnvironmentFileError) as raised:
        environment.load_project_environment(unreadable_env)
    assert str(unreadable_env) in str(raised.value) and 'Permission denied' in str(raised.value)


@pytest.mark.parametrize('command', [
    ['run', '--yes', '--no-view'],
    ['certify', 'react-agent', '--yes', '--no-view'],
    ['evaluate', 'react-agent', '--yes', '--no-view'],
])
def test_commands_report_an_unreadable_env_file_without_a_traceback(command, unreadable_env, monkeypatch, capsys):
    monkeypatch.setattr(run, 'LOGO_PAUSE_SECONDS', 0)
    code = cli([*command, '--env-file', str(unreadable_env)])
    captured = capsys.readouterr()
    assert code != 0
    assert 'Traceback' not in captured.out + captured.err
    assert 'Environment file could not be read' in captured.out + captured.err
