"""Shared execution preserves host options and SDK-independent storage semantics."""
from dataclasses import replace
import json

import pytest

from agentbench.runtime.contracts.execution import DockerCleanupError
from agentbench.sdk.contracts import SDKRunnerContext
from agentbench.sdk.integration.artifacts import FileArtifactStore
from agentbench.sdk.integration.execution import run_evaluation
from tests.test_sdk_execution import fake_services, source_agent, unchanged_stage


def context(services, **kwargs):
    return SDKRunnerContext(environ={}, model=None, trace_sink=None,
                            trace_max_bytes=1024, runtime_services=services, **kwargs)


def test_shared_execution_honors_explicit_model_without_mutating_environment(tmp_path):
    services, calls = fake_services()
    original = {'ABB_MODEL': 'environment-default'}
    host = replace(context(services), environ=original, model='selected-model')
    run_evaluation(source_agent(tmp_path), context=host, output=tmp_path / 'runs',
                   stage_agent=unchanged_stage)
    assert all(call['options']['environ']['ABB_MODEL'] == 'selected-model' for call in calls)
    assert original == {'ABB_MODEL': 'environment-default'}


def test_generation_without_prespecified_slots_uses_preparation_storage(tmp_path):
    services, calls = fake_services()
    store = FileArtifactStore(tmp_path / 'suite')
    directory = run_evaluation(source_agent(tmp_path), context=context(services, artifacts=store),
                               output=tmp_path / 'runs', stage_agent=unchanged_stage,
                               execute_agent=False)
    assert directory.is_relative_to(store.directory)
    assert 'preparation' in directory.parts
    assert [call['role'] for call in calls] == ['controller']
    assert calls[0]['settings']['isolated_agent'] is False
    assert calls[0]['closed'] == 1 and calls[0]['validated'] == []


@pytest.mark.parametrize('relative', ['.', '../outside', '/absolute', 'C:/outside'])
def test_private_files_cannot_escape_controller_storage(tmp_path, relative):
    services, calls = fake_services()
    source = tmp_path / 'rubric.json'
    source.write_text('{}')
    with pytest.raises(ValueError, match='relative paths'):
        run_evaluation(source_agent(tmp_path), context=context(services), output=tmp_path / 'runs',
                       stage_agent=unchanged_stage, private_files={relative: source})
    assert calls == []
    status = json.loads(next((tmp_path / 'runs').glob('*/run.json')).read_text())
    assert status['status'] == 'failed' and status['cleanup_status'] == 'not_started'


@pytest.mark.parametrize('require_identity', [False, True])
def test_private_sdk_configuration_does_not_implicitly_require_case_replay(tmp_path, require_identity):
    agent = source_agent(tmp_path)
    with (agent.path / 'agent.toml').open('a') as stream:
        stream.write('[evaluation.workspace]\npath="/home/agent/workspace"\ninitial_state="empty"\n')
    source = tmp_path / 'rubric.json'
    source.write_text('{"instructions":"private judge rules"}')
    services, calls = fake_services()
    arguments = dict(context=context(services), output=tmp_path / 'runs', stage_agent=unchanged_stage,
                     private_files={'rubric.json': source}, require_workspace_identity=require_identity)
    if require_identity:
        with pytest.raises(ValueError, match='no workspace contract'):
            run_evaluation(agent, **arguments)
        assert calls == []
    else:
        directory = run_evaluation(agent, **arguments)
        assert (directory / 'sdk-repo/rubric.json').read_bytes() == source.read_bytes()
        assert len(calls) == 2


def test_controller_cleanup_failure_still_closes_agent_and_records_outcome(tmp_path):
    services, calls = fake_services()
    original = services.create_docker_runtime

    def create_runtime(**options):
        runtime = original(**options)
        start = runtime.start

        def start_with_cleanup_failure(*args, **kwargs):
            session = start(*args, **kwargs)
            if not options['run_id'].endswith('-agent'):
                close = session.close

                def fail_close():
                    close()
                    raise DockerCleanupError('controller cleanup failed')

                session.close = fail_close
            return session

        runtime.start = start_with_cleanup_failure
        return runtime

    services.create_docker_runtime = create_runtime
    with pytest.raises(DockerCleanupError, match='controller cleanup failed'):
        run_evaluation(source_agent(tmp_path), context=context(services), output=tmp_path / 'runs',
                       stage_agent=unchanged_stage)
    assert all(call['closed'] == 1 for call in calls)
    status = json.loads(next((tmp_path / 'runs').glob('*/run.json')).read_text())
    assert status['status'] == 'failed' and status['cleanup_status'] == 'failed'
