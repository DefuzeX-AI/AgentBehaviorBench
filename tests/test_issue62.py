"""Issue #62: a generated Case the host cannot read is not reported as never generated."""
import json
import pathlib
from types import SimpleNamespace

import pytest

from agentbench.sdk.common.artifacts import Artifacts
from agentbench.sdk.plugin.kuma.benchmark import KumaContainerRunner
from agentbench.sdk.plugin.kuma.diagnostics import collect_artifacts, failure_message, unreadable_reason


def _deny(monkeypatch, *names):
    """Make named artifacts raise EACCES on open, independent of the test's uid."""
    original = pathlib.Path.open

    def open_(self, *args, **kwargs):
        if self.name in names:
            raise PermissionError(13, 'Permission denied', str(self))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, 'open', open_)


def test_unreadable_collection_names_the_file_and_the_saved_cases(tmp_path, monkeypatch):
    registration = SimpleNamespace(path=tmp_path / 'agent', case_count=1, agent_id='test-agent')
    registration.path.mkdir()
    (registration.path / 'requirement.md').write_text('An offline test Agent')
    directory = tmp_path / 'generated'

    def evaluate(agent, **kwargs):
        # The container finished: collection and Case file exist, and were billed.
        files = Artifacts(directory, environ={})
        files.save('run.json', {'status': 'succeeded', 'agent_id': agent.agent_id})
        kwargs['on_artifacts_ready'](directory)
        files.save('evaluation/manifest.json', {'phase': 'batch_generated', 'count': 1, 'failed_count': 0})
        files.save('evaluation/case-collection.json', {'schema': 'abb.case_collection.v2', 'cases': []})
        files.save('evaluation/cases/abb-case-0001.json', {'case': {'case_id': 'paid-case'}})
        _deny(monkeypatch, 'case-collection.json')
        return directory

    monkeypatch.setattr('agentbench.sdk.plugin.kuma.benchmark.evaluate', evaluate)
    with pytest.raises(RuntimeError) as raised:
        KumaContainerRunner(environ={'KUMA_API_KEY': 'offline'}).prepare_case_batch(registration)
    message = str(raised.value)
    assert 'host cannot read' in message and 'evaluation/case-collection.json' in message
    assert 'abb-case-0001.json' in message
    assert 'Case batch generation failed' not in message
    assert 'Permission denied' in message and 'owner uid' in message


def test_unreadable_required_artifact_is_reported_first(tmp_path, monkeypatch):
    files = Artifacts(tmp_path, environ={})
    files.save('evaluation/manifest.json', {'phase': 'judge', 'judge': 'received'})
    _deny(monkeypatch, 'manifest.json')
    artifacts = collect_artifacts(tmp_path, {'status': 'failed'}, environ={})
    assert len(artifacts['unreadable_artifacts']) == 1
    assert artifacts['unreadable_artifacts'][0].startswith('evaluation/manifest.json: Permission denied')
    assert failure_message(artifacts).startswith('unreadable artifact evaluation/manifest.json')


def test_absent_and_readable_artifacts_are_not_unreadable(tmp_path):
    assert unreadable_reason(tmp_path, 'evaluation/manifest.json') is None
    Artifacts(tmp_path, environ={}).save('evaluation/manifest.json', {'phase': 'finished'})
    assert unreadable_reason(tmp_path, 'evaluation/manifest.json') is None
    assert 'unreadable_artifacts' not in collect_artifacts(tmp_path, {}, environ={})


def test_real_owner_only_file_of_another_uid_is_unreadable(tmp_path):
    """Exercise the real mode check when the suite does not run as root."""
    if not hasattr(__import__('os'), 'geteuid') or __import__('os').geteuid() == 0:
        pytest.skip('root reads owner-only files of every uid')
    path = tmp_path / 'evaluation/case-collection.json'
    path.parent.mkdir()
    path.write_text(json.dumps({}))
    path.chmod(0o000)
    try:
        reason = unreadable_reason(tmp_path, 'evaluation/case-collection.json')
    finally:
        path.chmod(0o600)
    assert reason is not None and 'mode 0000' in reason


def test_inaccessible_parent_is_not_reported_as_absent(tmp_path):
    import os
    if not hasattr(os, 'geteuid') or os.geteuid() == 0:
        pytest.skip('requires an unprivileged POSIX user')
    path = tmp_path / 'evaluation' / 'case-collection.json'
    path.parent.mkdir()
    path.write_text('{}')
    path.parent.chmod(0o000)
    try:
        with pytest.raises(PermissionError):
            path.read_text()
        reason = unreadable_reason(tmp_path, 'evaluation/case-collection.json')
        assert reason is not None and 'Permission denied' in reason
    finally:
        path.parent.chmod(0o700)
