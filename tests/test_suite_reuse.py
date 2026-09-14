"""Linked fresh Suites reuse official Case files without old execution results."""

from dataclasses import replace
import json
from types import SimpleNamespace

import pytest

from agentbench.cli.sessions.recovery import execute_recovery
from agentbench.cli.sessions.reuse import execute_reuse, prepare_reuse
from agentbench.harness.session import SuiteProvenanceError, SuiteStore, read_snapshot

from tests.test_suite_resume import make_agent, make_case, runner_for, save_result


@pytest.fixture(autouse=True)
def isolated_reference_index(tmp_path, monkeypatch):
    from agentbench.cli.sessions import recovery, reuse
    monkeypatch.setattr(reuse, 'PROJECT_ROOT', tmp_path)
    monkeypatch.setattr(recovery, 'PROJECT_ROOT', tmp_path)


def original_suite(tmp_path, *, agents=1, cases=2, configuration=None):
    first = make_agent(tmp_path, cases)
    selected = tuple(replace(first, agent_id=f'agent-{index}') for index in range(agents))
    with SuiteStore.begin(tmp_path / 'suites', 'suite_original', selected,
                          configuration=configuration) as store:
        for agent in selected:
            for index in range(cases):
                case = store.retain_case(agent.agent_id, make_case(tmp_path / 'generation', index))
                save_result(store, agent, case, verdict='issue')
        store.append({'event': 'old_trace', 'output': 'OLD_ATTEMPT_OUTPUT_ONLY'})
        return store.directory, selected


def test_changed_code_reuses_all_original_cases_in_a_new_suite_without_old_results(tmp_path):
    source, agents = original_suite(tmp_path, agents=2, cases=2)
    previous_events = (source / 'events.json').read_bytes()
    (agents[0].path / 'agent.py').write_text('def invoke(value): return "updated code"\n')
    runner, factory = runner_for(tmp_path)
    with pytest.raises(SuiteProvenanceError):
        execute_recovery(source, environ={}, runner=runner)
    created = []
    execution = execute_reuse(source, environ={}, runner=runner, suite_id='suite_new', on_created=created.append)
    assert execution.directory == source.parent / 'suite_new'
    assert created == [execution.directory]
    assert len(factory.executed) == 4 and factory.generated == factory.recovered == []
    assert execution.result.items[0].completed_case_count == execution.result.items[1].completed_case_count == 2
    assert (source / 'events.json').read_bytes() == previous_events
    child_text = (execution.directory / 'events.json').read_text()
    assert 'OLD_ATTEMPT_OUTPUT_ONLY' not in child_text
    child = read_snapshot(execution.directory)
    assert child['origin_suite_id'] == 'suite_original'
    assert child['counts']['planned'] == child['counts']['completed'] == 4
    with SuiteStore.open(source) as old, SuiteStore.open(execution.directory) as new:
        assert old.plan['provenance_sha256'] != new.plan['provenance_sha256']
        for agent in agents:
            for old_case, new_case in zip(old.prepared_cases(agent.agent_id), new.prepared_cases(agent.agent_id)):
                assert old_case.case_id == new_case.case_id
                assert old_case.artifact_sha256 == new_case.artifact_sha256
                assert old_case.content_sha256 == new_case.content_sha256
                assert old_case.artifact_path.read_bytes() == new_case.artifact_path.read_bytes()
                assert old_case.artifact_path != new_case.artifact_path
    for job in child['jobs']:
        for case in job['cases']:
            assert len(case['attempts']) == 1
            assert case['attempts'][0]['attempt_number'] == 1
            assert not case['attempts'][0]['attempt_id'].startswith('initial-')
            assert case['origin']['suite_id'] == 'suite_original'


def test_preparation_of_reused_suite_copies_cases_but_no_attempts_or_verdicts(tmp_path):
    source, _ = original_suite(tmp_path)
    runner, factory = runner_for(tmp_path)
    directory, configured = prepare_reuse(source, environ={}, runner=runner, suite_id='suite_prepared')
    assert configured is runner and factory.executed == []
    snapshot = read_snapshot(directory)
    assert snapshot['counts']['completed'] == snapshot['counts']['judge_received'] == 0
    for case in snapshot['jobs'][0]['cases']:
        assert case['attempts'] == [] and case['result'] is None
        assert case['prepared_case']['case_id'] == case['origin']['case_id']
    assert all(event['event'] not in {'case_started', 'case_completed', 'agent_completed'}
               for event in json.loads((directory / 'events.json').read_text()))


@pytest.mark.parametrize('failure', ['missing', 'corrupt'])
def test_any_unusable_original_case_rejects_before_a_new_suite_is_created(tmp_path, failure):
    source, agents = original_suite(tmp_path)
    with SuiteStore.open(source) as original:
        case = original.prepared_case(agents[0].agent_id, 1)
    if failure == 'missing':
        case.artifact_path.unlink()
    else:
        case.artifact_path.write_text('{"changed": true}')
    runner, factory = runner_for(tmp_path)
    destination = tmp_path / 'new-root'
    with pytest.raises(SuiteProvenanceError):
        execute_reuse(source, environ={}, root=destination, runner=runner, suite_id='suite_invalid')
    assert not destination.exists()
    assert factory.executed == factory.generated == factory.recovered == []


def test_model_and_sdk_step_overrides_reach_the_normal_runner_builder(tmp_path, monkeypatch):
    from agentbench.cli.sessions import reuse
    source, _ = original_suite(tmp_path, configuration={
        'model': 'provider/old', 'sdk_options': {'max_steps': 2, 'custom_option': 'retained'},
        'runtime_source_sha256': 'old-code', 'workers': 3})
    captured = []
    def build(configuration, environment):
        captured.append(configuration)
        return SimpleNamespace(configuration={**configuration, 'runtime_source_sha256': 'current-code'})
    monkeypatch.setattr(reuse, 'build_saved_runner', build)
    monkeypatch.setattr(reuse, 'runner_configuration', lambda runner: runner.configuration)
    directory, _ = prepare_reuse(source, environ={}, model='provider/new', max_steps=5,
                                 suite_id='suite_overrides')
    assert captured[0]['model'] == 'provider/new'
    assert captured[0]['sdk_options'] == {'max_steps': 5, 'custom_option': 'retained'}
    with SuiteStore.open(directory) as child:
        assert child.plan['configuration']['runtime_source_sha256'] == 'current-code'
        assert child.plan['configuration']['workers'] == 3
        assert child.plan['configuration']['model'] == 'provider/new'


def test_reuse_rejects_same_suite_identity_and_unapplied_injected_overrides(tmp_path):
    source, _ = original_suite(tmp_path)
    runner, _ = runner_for(tmp_path)
    with pytest.raises(ValueError, match='new Suite identity'):
        prepare_reuse(source, environ={}, runner=runner, suite_id='suite_original')
    with pytest.raises(ValueError, match='report its applied configuration'):
        prepare_reuse(source, environ={}, runner=runner, model='provider/new', suite_id='suite_wrong_model')
    assert not (source.parent / 'suite_wrong_model').exists()


def test_reuse_command_is_registered_with_independent_source_and_destination_options():
    from agentbench.cli.main import build_parser
    args = build_parser().parse_args(['reuse', 'suite_original', '--suite-root', '/old/suites',
        '--output-root', '/new/suites', '--model', 'provider/model', '--max-steps', '5'])
    assert args.command == 'reuse' and args.suite == 'suite_original'
    assert args.suite_root == '/old/suites' and args.output_root == '/new/suites'
    assert args.model == 'provider/model' and args.max_steps == 5
    assert callable(args.command_handler)


def test_incomplete_linked_suite_never_generates_replacement_cases(tmp_path):
    source, agents = original_suite(tmp_path)
    with SuiteStore.open(source) as old:
        saved = old.prepared_case(agents[0].agent_id, 0)
    with SuiteStore.begin(source.parent, 'suite_incomplete_copy', agents,
                          origin_suite_id='suite_original') as child:
        child.retain_case(agents[0].agent_id, saved)
        directory = child.directory
    runner, factory = runner_for(tmp_path)
    result = execute_recovery(directory, environ={}, runner=runner)
    assert [index for index, *_ in factory.executed] == [0]
    assert factory.generated == []
    assert result.items[0].case_results[1].error_type == 'RecoveryRequired'
    assert 'replacement Case generation is disabled' in result.items[0].case_results[1].error_message


def test_source_and_custom_destination_suites_are_indexed_for_cleanup_protection(tmp_path):
    from agentbench.harness.session.references import collect_suite_references
    source, _ = original_suite(tmp_path)
    runner, _ = runner_for(tmp_path)
    directory, _ = prepare_reuse(source, environ={}, root=tmp_path / 'external-suites', runner=runner,
                                 suite_id='suite_external')
    references = {entry.suite_id: entry.directory for entry in collect_suite_references(tmp_path)}
    assert references == {'suite_original': source, 'suite_external': directory}
