"""A selected recovery must not authorize replay of another interrupted Attempt."""

import pytest

from agentbench.cli.sessions.recovery import execute_recovery
from agentbench.harness.result import CaseResult
from agentbench.harness.session import SuiteStore, read_snapshot

from tests.test_suite_resume import make_agent, make_case, runner_for


@pytest.fixture(autouse=True)
def isolated_reference_index(tmp_path, monkeypatch):
    from agentbench.cli.sessions import recovery
    monkeypatch.setattr(recovery, 'PROJECT_ROOT', tmp_path)


def interrupted_suite(tmp_path, status, *, located=True, prior_failure=False):
    agent = make_agent(tmp_path, 2)
    identity = {'agent_id': agent.agent_id, 'case_index': 1, 'job_id': 'original-job',
                'attempt_id': 'original-attempt', 'attempt_number': 2 if status == 'retrying' else 1}
    directory = str(tmp_path / 'original-artifacts')
    with SuiteStore.begin(tmp_path / 'suites', 'suite_selection', [agent]) as store:
        for index in range(2):
            store.retain_case(agent.agent_id, make_case(tmp_path / 'generation', index))
        store.append({'event': 'attempt_dispatched', **identity,
                      **({'artifact_directory': directory} if located and not prior_failure else {})})
        if prior_failure:
            result = CaseResult(agent.agent_id, 1, identity['job_id'], 'failed', 'case-1',
                error_type='RequestPending', error_message='Judge request remains pending',
                artifacts={'directory': directory, 'sdk_request': {'request_id': 'original-request',
                    'status': 'running'}, 'recovery': {'action': 'resume_request', 'automatic': True}},
                attempt_id=identity['attempt_id'], attempt_number=identity['attempt_number'])
            store.append({'event': 'case_attempt_failed', **identity, 'case_result': result})
        if status != 'dispatched':
            store.append({'event': 'case_started', **identity})
        if status == 'waiting_judge':
            store.append({'event': 'progress', **identity, 'stage': 'judge'})
        if status == 'reconciling':
            store.append({'event': 'case_recovery_started', **identity})
        return store.directory, agent


@pytest.mark.parametrize('status', ['dispatched', 'running', 'retrying', 'waiting_judge', 'reconciling'])
@pytest.mark.parametrize('replay', [False, True])
def test_retrying_sibling_keeps_unresolved_attempt_recovery_only(tmp_path, status, replay):
    directory, agent = interrupted_suite(tmp_path, status)
    runner, factory = runner_for(tmp_path)
    execute_recovery(directory, environ={}, runner=runner, selection={(agent.agent_id, 0)}, replay=True)

    pending = read_snapshot(directory)['jobs'][0]['cases'][1]
    assert pending['execution_status'] == 'blocked'
    assert pending['recovery_action'] == 'resume_request'
    assert pending['active_attempt_id'] == 'original-attempt'

    result = execute_recovery(directory, environ={}, runner=runner,
                              selection={(agent.agent_id, 1)} if replay else None, replay=replay)
    assert [index for index, *_ in factory.executed] == [0]
    assert factory.generated == []
    assert len(factory.recovered) == 1
    index, previous, identity = factory.recovered[0]
    assert index == 1 and previous.artifacts['directory'] == str(tmp_path / 'original-artifacts')
    assert identity['attempt_id'] == result.items[0].case_results[1].attempt_id == 'original-attempt'
    assert identity['attempt_number'] == (2 if status == 'retrying' else 1)
    assert len(read_snapshot(directory)['jobs'][0]['cases'][1]['attempts']) == 1

    # A further whole-Suite resume keeps both reports without another dispatch.
    execute_recovery(directory, environ={}, runner=runner)
    assert len(factory.executed) == len(factory.recovered) == 1
    with SuiteStore.open(directory) as store:
        completed = [event for event in store.events
                     if event['event'] == 'case_completed' and event.get('case_index') == 0]
        assert len(completed) == 1


def test_unselected_reconciling_attempt_preserves_prior_request_and_directory(tmp_path):
    directory, agent = interrupted_suite(tmp_path, 'reconciling', prior_failure=True)
    runner, factory = runner_for(tmp_path)
    execute_recovery(directory, environ={}, runner=runner, selection={(agent.agent_id, 0)})
    execute_recovery(directory, environ={}, runner=runner)
    assert [index for index, *_ in factory.executed] == [0]
    assert len(factory.recovered) == 1
    previous = factory.recovered[0][1]
    assert previous.artifacts['sdk_request']['request_id'] == 'original-request'
    assert previous.artifacts['directory'] == str(tmp_path / 'original-artifacts')
    assert previous.artifacts['recovery']['action'] == 'inspect_attempt'


def test_unselected_unlocated_attempt_never_becomes_replayable(tmp_path):
    directory, agent = interrupted_suite(tmp_path, 'dispatched', located=False)
    runner, factory = runner_for(tmp_path)
    execute_recovery(directory, environ={}, runner=runner, selection={(agent.agent_id, 0)})
    pending = read_snapshot(directory)['jobs'][0]['cases'][1]
    assert pending['execution_status'] == 'blocked'
    assert pending['can_retry'] is False
    execute_recovery(directory, environ={}, runner=runner, selection={(agent.agent_id, 1)}, replay=True)
    assert [index for index, *_ in factory.executed] == [0]
    assert factory.recovered == factory.generated == []
    pending = read_snapshot(directory)['jobs'][0]['cases'][1]
    assert pending['active_attempt_id'] == 'original-attempt'
    assert len(pending['attempts']) == 1
