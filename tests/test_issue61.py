"""Issue #61: the container user can read the settings the host mounts for it."""
import json
import os
import stat

import pytest

from agentbench.runtime.docker.policy import DockerPolicy
from agentbench.runtime.docker.runtime import DockerRuntimeError, _share_input_mount
from agentbench.sdk.common.artifacts import Artifacts
from agentbench.sdk.plugin.kuma import worker


def test_agent_containers_preserve_the_image_user():
    # A numeric override has no corresponding passwd/HOME entry in arbitrary
    # Agent images and can make their private files unreadable.
    arguments = DockerPolicy().run_arguments()
    assert not any(argument.startswith('--user') for argument in arguments)
    assert {'--cap-drop=ALL', '--security-opt=no-new-privileges'} <= set(arguments)


def test_owner_only_settings_become_readable_by_another_container_uid(tmp_path):
    inputs = tmp_path / 'request'
    inputs.mkdir(mode=0o700)
    # The real writer: atomic JSON writes are owner-only.
    Artifacts(tmp_path, environ={}).save('request/evaluation.json', {'mode': 'generate', 'count': 1})
    settings = inputs / 'evaluation.json'
    assert stat.S_IMODE(settings.stat().st_mode) & 0o077 == 0

    _share_input_mount(inputs)

    assert stat.S_IMODE(settings.stat().st_mode) & 0o004
    assert stat.S_IMODE(inputs.stat().st_mode) & 0o005 == 0o005
    # Only read access is added; the mount stays read-only in the container.
    assert stat.S_IMODE(settings.stat().st_mode) & 0o022 == 0


def test_input_mount_rejects_links(tmp_path):
    inputs = tmp_path / 'request'
    inputs.mkdir()
    (tmp_path / 'outside.json').write_text('{}')
    (inputs / 'evaluation.json').symlink_to(tmp_path / 'outside.json')
    with pytest.raises(DockerRuntimeError, match='symlinks'):
        _share_input_mount(inputs)


def _unreadable(monkeypatch, target):
    original = type(target).read_text

    def read_text(self, *args, **kwargs):
        if self == target:
            raise PermissionError(13, 'Permission denied', str(self))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(type(target), 'read_text', read_text)


def test_worker_names_unreadable_settings_instead_of_running_empty(tmp_path, monkeypatch, capsys):
    settings = tmp_path / 'evaluation.json'
    settings.write_text(json.dumps({'mode': 'generate', 'count': 1}))
    settings.chmod(0o600)
    output = tmp_path / 'output'
    output.mkdir()
    _unreadable(monkeypatch, settings)
    monkeypatch.setattr(worker, 'execute', lambda *a, **kw: pytest.fail('must not run with empty settings'))
    monkeypatch.setattr('sys.argv', ['worker', '--settings', str(settings), '--output', str(output)])

    assert worker.main() == 1

    error = json.loads((output / 'error.json').read_text())
    assert error['phase'] == 'startup' and error['type'] == 'EvaluationSettingsError'
    assert str(settings) in error['message'] and 'permission denied' in error['message']
    assert f'uid {os.getuid()}' in error['message'] and 'mode 0600' in error['message']
    assert error['message'] in capsys.readouterr().err


def test_worker_rejects_missing_settings(tmp_path, monkeypatch):
    output = tmp_path / 'output'
    output.mkdir()
    monkeypatch.setattr(worker, 'execute', lambda *a, **kw: pytest.fail('must not run with empty settings'))
    monkeypatch.setattr('sys.argv', ['worker', '--settings', str(tmp_path / 'absent.json'),
                                     '--output', str(output)])
    assert worker.main() == 1
    assert 'missing' in json.loads((output / 'error.json').read_text())['message']


def test_startup_failure_reaches_the_host_failure_message(tmp_path, monkeypatch):
    from agentbench.sdk.plugin.kuma.diagnostics import collect_artifacts, failure_message
    settings = tmp_path / 'request/evaluation.json'
    settings.parent.mkdir()
    settings.write_text('{}')
    output = tmp_path / 'evaluation'
    output.mkdir()
    _unreadable(monkeypatch, settings)
    monkeypatch.setattr('sys.argv', ['worker', '--settings', str(settings), '--output', str(output)])
    assert worker.main() == 1
    artifacts = collect_artifacts(tmp_path, {'status': 'failed'}, environ={})
    assert artifacts['phase'] == 'startup'
    assert 'Cannot read evaluation settings' in failure_message(artifacts)
