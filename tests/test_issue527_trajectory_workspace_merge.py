"""Verify the current-main trajectory contract and local snapshot coexist."""
import json
from types import SimpleNamespace

import pytest

from agentbench.sdk import judges
from agentbench.sdk.plugin.local.file_evidence import capture_workspace
from tests.test_issue527_workspace_evidence import build_case, policy


def test_judge_binds_both_current_main_trajectory_and_workspace_evidence(tmp_path):
    root = tmp_path / 'run'
    root.mkdir()
    document = build_case(root)
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    (workspace / 'hello.py').write_text('print("hello")\n')
    capture_workspace(workspace, root, policy(), environ={})
    (root / 'run.json').write_text(json.dumps({'workspace_evidence': 'complete'}))
    (root / 'trajectory.json').write_text(json.dumps({'schema': 'test.fixture', 'steps': []}))

    request = judges.build_request(root, SimpleNamespace(agent_id='openaeon'), document)
    assert request['workspace_evidence'] == 'local-workspace-evidence.json'
    assert {'trajectory.json', 'local-workspace-evidence.json'} <= set(request['attachments'])
    judges.validate_evidence(request, root)
    (root / 'trajectory.json').write_text('{}')
    with pytest.raises(ValueError, match='evidence changed'):
        judges.validate_evidence(request, root)


def test_main_trajectory_runs_before_snapshot_and_both_survive_cleanup(tmp_path, monkeypatch):
    import agentbench.trajectory as trajectory
    from agentbench.sdk.integration.execution import run_evaluation
    from tests.test_sdk_execution import fake_services, source_agent, unchanged_stage
    from tests.test_sdk_execution_lifecycle import context

    agent = source_agent(tmp_path)
    with (agent.path / 'agent.toml').open('a') as stream:
        stream.write('[evaluation.workspace]\npath="/workspace/project"\ninitial_state="empty"\n'
                     '[evaluation.file_evidence]\ntrack_files=true\n')
    services, calls = fake_services()
    events = []
    original = trajectory.write

    def write(directory, **kwargs):
        assert all(call['closed'] == 1 for call in calls)
        events.append('trajectory')
        return original(directory, **kwargs)

    def capture(root, destination, workspace_policy, *, environ):
        assert all(call['closed'] == 1 for call in calls)
        assert root.is_dir()
        events.append('workspace')
        (root / 'hello.py').write_text('hello\n')
        return capture_workspace(root, destination, workspace_policy, environ=environ)

    monkeypatch.setattr(trajectory, 'write', write)
    result = run_evaluation(agent, context=context(services), output=tmp_path / 'runs',
                            stage_agent=unchanged_stage, capture_workspace=capture)
    status = json.loads((result / 'run.json').read_text())
    assert events == ['trajectory', 'workspace']
    assert status['status'] == 'succeeded' and status['workspace_evidence'] == 'complete'
    assert status['trajectory']['status'] in ('complete', 'partial')
    assert json.loads((result / 'trajectory.json').read_text())['status'] == status['trajectory']['status']
    assert json.loads((result / 'local-workspace-evidence.json').read_text())['files'][0]['path'] == 'hello.py'
