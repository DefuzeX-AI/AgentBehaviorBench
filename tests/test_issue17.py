"""Issue #17: invalid viewer inputs are concise command errors."""
import pytest

from agentbench.cli.main import cli


@pytest.mark.parametrize('directory', [False, True])
def test_invalid_artifact_has_no_traceback(tmp_path, capsys, directory):
    target = tmp_path/'result.json'
    if directory:
        target.mkdir()
    assert cli(['view', str(target)]) == 2
    assert 'Result' in capsys.readouterr().out


@pytest.mark.parametrize('port', ['-1', '65536'])
def test_invalid_port_rejected_during_argument_parsing(port):
    with pytest.raises(SystemExit) as caught:
        cli(['view', 'unused.json', '--port', port])
    assert caught.value.code == 2
