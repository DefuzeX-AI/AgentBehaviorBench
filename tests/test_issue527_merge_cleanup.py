"""The merged SDK must clean workspaces even when snapshot-error reporting fails."""
import json

import pytest


def test_workspace_cleanup_survives_snapshot_diagnostic_write_failure(tmp_path, monkeypatch):
    from agentbench.sdk.common.artifacts import Artifacts
    from agentbench.sdk.integration.execution import run_evaluation
    from tests.test_sdk_execution import fake_services, source_agent, unchanged_stage
    from tests.test_sdk_execution_lifecycle import context

    agent = source_agent(tmp_path)
    with (agent.path / 'agent.toml').open('a', encoding='utf-8') as stream:
        stream.write('[evaluation.workspace]\npath="/workspace/project"\ninitial_state="empty"\n'
                     '[evaluation.file_evidence]\ntrack_files=true\n')
    services, calls = fake_services()
    save = Artifacts.save

    def reject_snapshot_error(self, name, value, *args, **kwargs):
        if name == 'local-workspace-evidence.json':
            raise OSError('snapshot diagnostic write failed')
        return save(self, name, value, *args, **kwargs)

    def fail_capture(*args, **kwargs):
        raise ValueError('snapshot capture failed')

    monkeypatch.setattr(Artifacts, 'save', reject_snapshot_error)
    runs = tmp_path / 'runs'
    with pytest.raises(OSError, match='snapshot diagnostic write failed'):
        run_evaluation(agent, context=context(services), output=runs,
                       stage_agent=unchanged_stage, capture_workspace=fail_capture)
    assert all(call['closed'] == 1 for call in calls)
    assert not list(runs.glob('.abb-workspace-*'))
    directory = next(path for path in runs.iterdir() if path.is_dir())
    assert json.loads((directory / 'run.json').read_text())['source_cleanup_status'] == 'succeeded'
