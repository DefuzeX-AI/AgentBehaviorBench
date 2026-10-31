"""Issue detection uses ordered Cases, isolated execution, and independent evidence."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

from agentbench.experiments.exp1 import Experiment1, SCHEMA
from agentbench.experiments.exp1_inputs import load_cases
from agentbench.experiments.exp1_metrics import aggregate, summarize
from agentbench.harness.ground_truth import detection
from agentbench.harness.ground_truth.issues import load_issue
from tests.test_ground_truth import reference_attempt, write_json
from tests.test_evaluation_service import project
from tests.test_sdk_defaults import inprocess_worker_permissions


def case(identity):
    return {'case_id': identity, 'inputs': [{'input_id': 'task', 'payload': identity}]}



def install_issue(service, number=1):
    unit = service.root / 'unit'
    folder = unit / 'ground_truth' / f'issue_{number}'
    write_json(folder / 'verify.case.json', {
        'issue': {'number': number, 'title': 'Secret reference title'},
        'expected': 'Echo the input.', 'defect': 'Adds a turn counter.',
        'Root cause': 'Fixture reference; never provided to target.', 'commit_version': 'a' * 40})
    reference_attempt(folder / 'runs/run-01/trajectory/reference', 'example')
    return folder



@pytest.fixture
def oracle(monkeypatch):
    model = SimpleNamespace(model='fixture', base_url='https://example.test')
    monkeypatch.setattr('agentbench.experiments.exp1.oracle_model', lambda _: model)
    return model



def answer(hit=True):
    return {'match': hit, 'reason': 'Observed execution evidence.',
            'reference_step_ids': ['runs/run-01/trajectory/reference/1'],
            'candidate_step_ids': [2 if hit else 1],
            'candidate_decisive_step': 2 if hit else None,
            'candidate_observation': 'The file says hello.' if hit else None}



def test_detection_prefixes_unknowns_and_fixed_denominator():
    def rows(hits):
        return {'tests': [{'hit': h} for h in hits]}
    issues = [rows([False] * 6 + [True] + [False] * 43), rows([False] * 50)]
    metrics = summarize(issues, 50)
    assert [metrics[f'Detection@{k}']['value'] for k in (1, 5, 10, 20, 50)] == [0, 0, .5, .5, .5]
    issues.append(rows([None] * 50))
    assert summarize(issues, 50)['Detection@10']['bounds'] == [1 / 3, 2 / 3]
    assert summarize(issues, 50)['Detection@10']['value'] is None
    assert summarize([rows([True])], 50)['Detection@50']['value'] == 1
    assert summarize([rows([False])], 50)['Detection@5']['status'] == 'pending'
    assert summarize([rows([True])], 30)['Detection@50']['status'] == 'outside_budget'



def test_issue_adapter_reads_current_layout_and_checks_identity(project):
    service, _, _ = project
    folder = install_issue(service)
    value = load_issue(service.root, 'example', 'issue_1')
    assert len(value['trajectories']) == 1
    assert value['definition']['issue']['number'] == 1
    path = folder / 'verify.case.json'
    doc = json.loads(path.read_text())
    doc['issue']['number'] = 2
    write_json(path, doc)
    with pytest.raises(ValueError, match='identity'):
        load_issue(service.root, 'example', 'issue_1')



def test_issue_adapter_requires_verify_case(project):
    service, _, _ = project
    folder = install_issue(service)
    current = folder / 'verify.case.json'
    legacy = folder / 'case.verified.json'
    document = json.loads(current.read_text())
    write_json(legacy, {**document, 'Root cause': 'Legacy copy'})
    assert load_issue(service.root, 'example', 'issue_1')['definition']['Root cause'] == document['Root cause']
    current.unlink()
    with pytest.raises(ValueError, match='unavailable'):
        load_issue(service.root, 'example', 'issue_1')



def test_issue_adapter_accepts_only_declared_historical_baseline_alias(project):
    service, _, _ = project
    folder = install_issue(service)
    path = folder / 'runs/run-01/trajectory/reference/trajectory.json'
    saved = json.loads(path.read_text(encoding='utf-8'))
    saved['agent_id'] = 'historical-before'
    saved['metadata']['historical_import'] = {
        'role': 'baseline', 'tested_base_commit': 'historical-commit'}
    write_json(path, saved)
    definition = folder / 'verify.case.json'
    document = json.loads(definition.read_text(encoding='utf-8'))
    document['commit_version'] = 'historical-commit'
    with pytest.raises(ValueError, match='another Agent'):
        load_issue(service.root, 'example', 'issue_1')
    document['reference_agent_aliases'] = ['historical-before']
    write_json(definition, document)
    assert load_issue(service.root, 'example', 'issue_1')['trajectories'][0]['agent_id'] == 'historical-before'
    saved['metadata']['historical_import']['tested_base_commit'] = 'different-commit'
    write_json(path, saved)
    with pytest.raises(ValueError, match='another Agent'):
        load_issue(service.root, 'example', 'issue_1')



def test_oracle_evidence_validation_failure_journal_and_explicit_retry(project, oracle, tmp_path):
    service, _, _ = project
    install_issue(service)
    reference = load_issue(service.root, 'example', 'issue_1')
    candidate = {**reference['trajectories'][0]}
    calls = []
    def invalid(*a, **k):
        calls.append(1)
        return {**answer(), 'candidate_step_ids': [999], 'candidate_decisive_step': 999}
    args = dict(directory=tmp_path / 'calls', environ={}, model=oracle)
    with pytest.raises(ValueError, match='unknown'):
        detection.assess(reference, candidate, ask=invalid, **args)
    with pytest.raises(ValueError, match='retry-failed'):
        detection.assess(reference, candidate, ask=invalid, **args)
    assert len(calls) == 2  # initial invalid decision plus one bounded evidence repair
    result = detection.assess(reference, candidate, ask=lambda *a, **k: answer(), retry_failed=True, **args)
    assert result['hit'] is True
    assert len(list((tmp_path / 'calls').rglob('*.json'))) == 2


def test_oracle_rejects_hallucinated_candidate_observation(project, oracle, tmp_path):
    service, _, _ = project
    install_issue(service)
    reference = load_issue(service.root, 'example', 'issue_1')
    candidate = reference['trajectories'][0]
    fabricated = {**answer(), 'candidate_observation': 'No files or directories found matching pattern'}
    with pytest.raises(ValueError, match='observation is absent'):
        detection.assess(reference, candidate, directory=tmp_path / 'calls',
                         environ={}, model=oracle, ask=lambda *a, **k: fabricated)


def test_observation_can_quote_parallel_tool_outputs_from_one_step():
    candidate = {'steps': [{'step_id': 1, 'output': {}, 'tool_logs': [
        {'outputs': 'first observed failure'}, {'outputs': 'second observed failure'}]}]}
    reply = {'match': True, 'candidate_decisive_step': 1,
             'candidate_observation': 'first observed failure\nsecond observed failure'}
    detection.validate_candidate_observation(reply, candidate)
    reply['candidate_observation'] = 'first observed failure\nnever observed'
    with pytest.raises(ValueError, match='observation is absent'):
        detection.validate_candidate_observation(reply, candidate)


def test_oracle_can_request_full_context_and_reuse_both_calls(project, oracle, tmp_path):
    service, _, _ = project
    install_issue(service)
    reference = load_issue(service.root, 'example', 'issue_1')
    candidate = reference['trajectories'][0]
    requests = []
    def ask(model, *, system, payload):
        requests.append(payload)
        if payload['evidence_view'] == 'execution':
            return {'request_full_context': True, 'reason': 'Need request message history'}
        assert payload['shared_model_context']
        return answer()
    args = dict(directory=tmp_path / 'calls', environ={}, model=oracle, ask=ask)
    assert detection.assess(reference, candidate, **args)['hit'] is True
    assert [p['evidence_view'] for p in requests] == ['execution', 'full_context']
    assert detection.assess(reference, candidate, **args)['cache_reused']
    assert len(requests) == 2


def test_oracle_repairs_invalid_citation_once_from_candidate_evidence(project, oracle, tmp_path):
    service, _, _ = project
    install_issue(service)
    reference = load_issue(service.root, 'example', 'issue_1')
    candidate = reference['trajectories'][0]
    requests = []
    def ask(model, *, system, payload):
        requests.append(payload)
        if len(requests) == 1:
            return {**answer(), 'candidate_step_ids': [999], 'candidate_decisive_step': 999}
        assert 'reference_trajectories' not in payload
        assert payload['candidate_trajectory']['steps'][1]['step_id'] == 2
        assert 'unknown trajectory step' in payload['validation_error']
        return answer()
    result = detection.assess(reference, candidate, directory=tmp_path / 'calls',
                              environ={}, model=oracle, ask=ask)
    assert result['hit'] is True and len(requests) == 2
    journal = json.loads(Path(result['call_path']).read_text(encoding='utf-8'))
    assert journal['repair_request']['payload']['previous_reply']['candidate_step_ids'] == [999]



def test_input_attribution_gap_does_not_override_case_verdict(project, oracle, tmp_path):
    service, _, _ = project
    install_issue(service)
    reference = load_issue(service.root, 'example', 'issue_1')
    candidate = deepcopy(reference['trajectories'][0])
    candidate.update(status='partial', warnings=['Model call has no confirmed Input.'])
    candidate['steps'][0]['input_ordinal'] = None
    original = deepcopy(candidate)
    def ask(model, *, system, payload):
        view = payload['candidate_trajectory']
        assert view['case_id'] == candidate['case_id']
        assert view['coverage'] == candidate['coverage']
        assert view['warnings'] == candidate['warnings']
        assert view['steps'][0]['input_ordinal'] is None
        assert view['steps'][0]['evidence'] == candidate['steps'][0]['evidence']
        assert view['steps'][0]['status'] == candidate['steps'][0]['status']
        return answer(False)
    result = detection.assess(reference, candidate, directory=tmp_path / 'calls', environ={}, model=oracle,
                              ask=ask)
    assert result['hit'] is False
    assert candidate == original
    with pytest.raises(ValueError, match='not truncated'):
        detection.assess(reference, candidate, directory=tmp_path / 'calls',
                          environ={'ABB_GT_MAX_BYTES': '10'}, model=oracle,
                          ask=lambda *a, **k: pytest.fail('Oversize'))


def test_missing_tool_outcome_remains_visible_and_inconclusive(project, oracle, tmp_path):
    service, _, _ = project
    install_issue(service)
    reference = load_issue(service.root, 'example', 'issue_1')
    candidate = deepcopy(reference['trajectories'][0])
    candidate.update(status='partial', warnings=['Tool execution was not observed.'])
    candidate['coverage']['unobserved_tool_executions'] = 1
    log = candidate['steps'][0]['tool_logs'][0]
    log.update(outputs=None, execution_status='not_observed', link='none')
    original = deepcopy(candidate)
    def ask(model, *, system, payload):
        view = payload['candidate_trajectory']
        assert view['coverage']['unobserved_tool_executions'] == 1
        assert view['steps'][0]['tool_logs'][0] == log
        return {**answer(None), 'reason': 'The required tool outcome is missing.'}
    result = detection.assess(reference, candidate, directory=tmp_path / 'calls',
                              environ={}, model=oracle, ask=ask)
    assert result['hit'] is None
    assert candidate == original


def test_context_request_preserves_diagnostics_and_unknown(project, oracle, tmp_path):
    service, _, _ = project
    install_issue(service)
    reference = load_issue(service.root, 'example', 'issue_1')
    candidate = deepcopy(reference['trajectories'][0])
    candidate.update(status='partial', warnings=['Input ownership is ambiguous.'])
    calls = []
    def ask(model, *, system, payload):
        calls.append(payload)
        assert payload['candidate_trajectory']['warnings'] == candidate['warnings']
        if len(calls) == 1:
            return {'request_full_context': True, 'reason': 'Need the conversation request.'}
        return {**answer(None), 'reason': 'The failure depends on an unavailable Input association.'}
    result = detection.assess(reference, candidate, directory=tmp_path / 'calls',
                              environ={}, model=oracle, ask=ask)
    assert result['hit'] is None and len(calls) == 2



def test_shared_provider_default_is_independent_of_judge_and_target(monkeypatch):
    seen = {}
    monkeypatch.setattr(detection, 'model_config', lambda env: seen.update(env))
    detection.oracle_model({'ABB_MODEL_PROVIDER': 'deepseek', 'ABB_MODEL': 'target',
                            'ABB_LOCAL_JUDGE_MODEL': 'legacy', 'ABB_GT_MODEL': 'legacy-gt',
                            'OPENROUTER_MODEL': 'default', 'OPENROUTER_API_KEY': 'test'})
    assert seen['ABB_MODEL_PROVIDER'] == 'deepseek'
    assert seen['OPENROUTER_MODEL'] == 'default'
    assert not {'ABB_MODEL', 'ABB_GT_MODEL', 'ABB_LOCAL_JUDGE_MODEL'} & seen.keys()


@pytest.mark.parametrize('provider,model,endpoint', [
    ('deepseek', 'deepseek-flash', 'https://api.deepseek.com'),
    ('openrouter', 'openai/gpt-4.1-mini', 'https://openrouter.ai/api/v1'),
])
def test_oracle_resolves_selected_provider_without_target_or_legacy_overrides(provider, model, endpoint):
    selected = detection.oracle_model({
        'ABB_MODEL_PROVIDER': provider, 'ABB_MODEL': 'target-only',
        'DEEPSEEK_MODEL': 'deepseek-flash', 'DEEPSEEK_API_KEY': 'test-ds-key',
        'OPENROUTER_MODEL': 'openai/gpt-4.1-mini', 'OPENROUTER_API_KEY': 'test-router-key',
        'ABB_GT_MODEL': 'legacy', 'ABB_GT_BASE_URL': 'https://legacy.invalid',
        'ABB_GT_API_KEY': 'test-legacy-key', 'ABB_LOCAL_JUDGE_MODEL': 'local-only',
    })
    assert selected.model == model
    assert selected.base_url == endpoint
    assert selected.api_key == ('test-ds-key' if provider == 'deepseek' else 'test-router-key')



def test_cli_result_is_read_only_and_needs_no_credentials(tmp_path, capsys, monkeypatch):
    from agentbench.cli.main import cli
    write_json(tmp_path / 'result.json', {'schema': 'abb.exp1.v1', 'status': 'completed'})
    monkeypatch.setattr('agentbench.cli.environment.load_execution_environment',
                        lambda *a, **k: pytest.fail('Read-only result must not load credentials'))
    assert cli(['exp1', 'result', '--experiment', str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'completed'



def test_legacy_round_aggregation_preserves_original_unit():
    from agentbench.experiments.exp1_metrics import summarize_rounds
    rows = [{'round_index': number, 'hit': hit, 'execution_wall_seconds': 1.5}
            for number, hits in [(1, [False, False]), (2, [None, False]), (3, [False, True])]
            for hit in hits]
    rounds = summarize_rounds(rows)
    assert [r['hit'] for r in rounds] == [False, None, True]
    assert all(r['case_count'] == 2 and r['execution_wall_seconds'] == 3 for r in rounds)
    assert summarize([{'tests': rounds}], 3)['Detection@1']['value'] == 0



def collection(path, cases):
    write_json(path, {'schema': 'abb.cases.v1', 'cases': cases})
    return path


@pytest.fixture
def prepared(project, oracle, monkeypatch):
    """Use real scheduling/storage with a local prepared target; never build or call models."""
    from agentbench.evaluation.targets import PreparedTarget
    from agentbench.harness.session.plan import source_digest
    service, agent, processes = project
    original = service._registration('example')
    manifest = original.path / 'agent.toml'
    manifest.write_text(manifest.read_text() +
        '\n[evaluation.workspace]\npath="/home/agent/work"\ninitial_state="empty"\n')
    path = service.root / 'prepared'
    shutil.copytree(original.path, path)
    target_manifest = path / 'agent.toml'
    target_manifest.write_text(target_manifest.read_text() + '\n[source]\nrevision="' + 'a' * 40 + '"\n')
    target = PreparedTarget(replace(original, path=path, requirement_path=path / 'requirement.md'),
                            'a' * 40, 'fingerprint', source_digest(path))
    calls = []
    def prepare(agent_id, revision, **kwargs):
        assert agent_id == 'example' and revision == target.revision
        calls.append(revision)
        return target
    monkeypatch.setattr(service, 'prepare', prepare)
    folder = install_issue(service)
    reference = load_issue(service.root, 'example', 'issue_1')
    candidate = {k: v for k, v in reference['trajectories'][0].items() if k != 'attempt'}
    # The Echo target has no LLM events; supply the existing complete trace fixture to the oracle.
    monkeypatch.setattr('agentbench.experiments.exp1.read_candidate', lambda *a, **k: candidate)
    return SimpleNamespace(service=service, agent=agent, processes=processes, target=target,
                           preparations=calls, folder=folder, candidate=candidate)


def experiment(f, ask, output=lambda _: None):
    return Experiment1(f.service.root, execution_service=f.service, ask=ask, output=output)


def test_collection_limits_order_and_absolute_file(tmp_path, monkeypatch):
    cases = [case(str(i)) for i in range(50, 0, -1)]
    path = collection(tmp_path / 'input.json', cases)
    assert load_cases(path) == cases
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match='absolute'):
        load_cases(Path('input.json'))
    with pytest.raises(ValueError, match='existing JSON'):
        load_cases(tmp_path)
    with pytest.raises(ValueError, match='existing JSON'):
        load_cases(tmp_path / 'absent.json')
    for count in (0, 51):
        collection(path, [case(str(i)) for i in range(count)])
        with pytest.raises(ValueError, match='1 and 50'):
            load_cases(path)


@pytest.mark.parametrize('cases', [
    [case('same'), case('same')],
    [{'case_id': 'bad', 'inputs': []}],
    [{'case_id': 'bad', 'inputs': [{'input_id': 'a', 'payload': 'x'}] * 2}],
    [{'case_id': 'bad', 'steps': ['Not the native Case contract']}],
    [None],
])
def test_invalid_cases_rejected(tmp_path, cases):
    with pytest.raises(ValueError):
        load_cases(collection(tmp_path / 'input.json', cases))


def test_cli_requires_issue_and_absolute_file_interface(tmp_path):
    from agentbench.cli.main import build_parser
    parser = build_parser()
    path = str(tmp_path / 'input.json')
    args = parser.parse_args(['exp1', 'run', 'example', '--issue', '1343', '--cases', path])
    assert args.issue == 1343 and args.cases == Path(path)
    assert not hasattr(args, 'tests') and not hasattr(args, 'workers')
    for arguments in [[], ['--cases', path], ['--issue', '1'], ['--case-dir', path]]:
        with pytest.raises(SystemExit):
            parser.parse_args(['exp1', 'run', 'example', *arguments])


@pytest.mark.parametrize('revision', [None, '', 'unknown', 'a' * 39])
def test_invalid_revision_blocks_preparation_and_execution(prepared, monkeypatch, revision):
    f = prepared
    path = f.folder / 'verify.case.json'
    definition = json.loads(path.read_text())
    definition['commit_version'] = revision
    write_json(path, definition)
    monkeypatch.setattr(f.service, 'execute', lambda *a, **k: pytest.fail('Must preflight'))
    cases_file = collection(f.service.root / 'input.json', [case('a')])
    with pytest.raises(ValueError, match='commit_version'):
        experiment(f, lambda *a, **k: pytest.fail('Must preflight')).run('example', cases_file, issue=1)
    assert not f.preparations


def test_second_case_hit_stops_execution_and_preserves_full_input(prepared):
    f = prepared
    submitted = [case('first'), {'case_id': 'second', 'inputs': [
        {'input_id': 'one', 'payload': 'remember blue'}, {'input_id': 'two', 'payload': 'recall'}]},
        case('third'), case('fourth'), case('fifth')]
    path = collection(f.service.root / 'input.json', submitted)
    observed, progress = [], []
    def ask(model, *, system, payload):
        observed.append(payload)
        assert len(f.agent.requests) == (1 if len(observed) == 1 else 3)
        assert all(p.closed for p in f.processes)
        assert 'finding_summary' not in payload
        return answer(len(observed) == 2)
    result = experiment(f, ask, progress.append).run('example', path, issue=1)
    assert result['schema'] == SCHEMA and result['score'] == 1 and result['first_hit'] == 2
    assert result['metrics']['Detection@1']['value'] == 0
    assert result['metrics']['Detection@5']['value'] == 1
    assert result['metrics']['Detection@10']['status'] == 'outside_budget'
    assert result['matched_case'] == submitted[1]
    assert json.loads(Path(result['matched_case_path']).read_text()) == submitted[1]
    assert len(result['issues'][0]['tests']) == 2
    assert result['issues'][0]['unexecuted_case_ids'] == ['third', 'fourth', 'fifth']
    assert result['issues'][0]['stop_reason'] == 'hit'
    assert [r['input'] for r in f.agent.requests] == ['first', 'remember blue', 'recall']
    assert 'Secret reference title' not in str(f.agent.requests)
    assert len(f.preparations) == 1
    plan = json.loads((Path(result['directory']) / 'plan.json').read_text())
    assert plan['prepared_targets']['issue_1']['revision'] == 'a' * 40
    assert plan['target']['source']['revision'] == 'a' * 40
    assert plan['issues'][0]['cases'] == submitted
    assert any('[1/5] first: 0' in message for message in progress)
    assert any('[2/5] second: 1' in message for message in progress)


def test_all_negative_cases_are_zero_with_independent_sessions_and_workspaces(prepared, monkeypatch):
    from agentbench.sdk.integration import execution
    f = prepared
    cases = [{'case_id': f'case-{i}', 'inputs': [
        {'input_id': 'a', 'payload': 'one'}, {'input_id': 'b', 'payload': 'two'}]} for i in range(3)]
    path = collection(f.service.root / 'input.json', cases)
    workspaces = []
    prepare_workspace = execution.prepare_workspace
    def inspect(root, destination, policy):
        assert not list(destination.iterdir())
        workspaces.append(destination)
        contract = prepare_workspace(root, destination, policy)
        (destination / 'marker').write_text('left by a Case')
        return contract
    monkeypatch.setattr(execution, 'prepare_workspace', inspect)
    execute = f.service.execute
    def check_execute(*args, **kwargs):
        assert kwargs['target'] is f.target
        assert kwargs['max_steps'] == 2
        assert kwargs['retry_policy'].max_retries == 0
        return execute(*args, **kwargs)
    monkeypatch.setattr(f.service, 'execute', check_execute)
    result = experiment(f, lambda *a, **k: answer(False)).run('example', path, issue=1)
    assert result['score'] == 0 and result['status'] == 'completed'
    assert result['matched_case'] is None and result['matched_case_path'] is None
    rows = result['issues'][0]['tests']
    assert len(rows) == 3 and all(r['hit'] is False for r in rows)
    assert len({r['suite'] for r in rows}) == 3
    pairs = [f.agent.requests[i:i+2] for i in range(0, 6, 2)]
    assert all(pair[0]['session_id'] == pair[1]['session_id'] for pair in pairs)
    assert len({pair[0]['session_id'] for pair in pairs}) == 3
    assert len(set(workspaces)) == len(workspaces)
    assert all(not path.exists() for path in workspaces)
    assert all(p.closed for p in f.processes)
    assert all(r['execution_wall_seconds'] > 0 for r in rows)
    for i, row in enumerate(rows, 1):
        saved = Path(result['directory']) / f'issue_1/repetitions/{i:04d}'
        assert json.loads((saved / 'execution.json').read_text())['wall_seconds'] == row['execution_wall_seconds']
        assert json.loads((saved / 'assessment.json').read_text())['hit'] is False


def test_execution_failure_stays_unknown_and_next_case_runs(prepared, monkeypatch):
    f = prepared
    path = collection(f.service.root / 'input.json', [case('bad'), case('good')])
    execute = f.service.execute
    calls = []
    def fail_once(*args, **kwargs):
        calls.append(args[1][0]['case_id'])
        if len(calls) == 1:
            raise RuntimeError('Infrastructure unavailable')
        return execute(*args, **kwargs)
    monkeypatch.setattr(f.service, 'execute', fail_once)
    result = experiment(f, lambda *a, **k: answer(False)).run('example', path, issue=1)
    assert calls == ['bad', 'good']
    assert result['score'] is None and result['status'] == 'partial'
    assert [r['hit'] for r in result['issues'][0]['tests']] == [None, False]
    assert result['metrics']['Detection@1']['bounds'] == [0, 1]
    assert 'Infrastructure unavailable' in result['issues'][0]['tests'][0]['reason']


def test_match_uses_frozen_cases_and_gt_without_execution_or_paid_reassessment(prepared, monkeypatch):
    f = prepared
    path = collection(f.service.root / 'input.json', [case('original')])
    service = experiment(f, lambda *a, **k: answer())
    result = service.run('example', path, issue=1)
    collection(path, [case('changed')])
    (f.folder / 'verify.case.json').unlink()
    monkeypatch.setattr(f.service, 'execute', lambda *a, **k: pytest.fail('Must not execute'))
    service.ask = lambda *a, **k: pytest.fail('Must reuse oracle journal')
    matched = service.match(result['directory'])
    assert matched['matched_case'] == case('original')
    assert matched['metrics'] == result['metrics']
    assert matched['issues'][0]['tests'][0]['cache_reused']
    monkeypatch.setattr('agentbench.experiments.exp1.oracle_model',
                        lambda _: SimpleNamespace(model='changed', base_url='https://example.test'))
    with pytest.raises(ValueError, match='frozen experiment'):
        service.match(result['directory'])


def test_failed_oracle_can_be_retried_without_executing_target(prepared, monkeypatch):
    f = prepared
    path = collection(f.service.root / 'input.json', [case('a')])
    service = experiment(f, lambda *a, **k: (_ for _ in ()).throw(RuntimeError('oracle unavailable')))
    result = service.run('example', path, issue=1)
    assert result['score'] is None
    monkeypatch.setattr(f.service, 'execute', lambda *a, **k: pytest.fail('Must not execute'))
    service.ask = lambda *a, **k: answer()
    assert service.match(result['directory'])['score'] is None
    result = service.match(result['directory'], retry_failed=True)
    assert result['score'] == 1
    assert len(f.agent.requests) == 1
    assert len(list(Path(result['directory']).glob('issue_1/repetitions/*/oracle-calls/*/*.json'))) == 2


def test_interruption_preserves_completed_cases_and_unresolved_attempt(prepared, monkeypatch):
    f = prepared
    path = collection(f.service.root / 'input.json', [case('one'), case('two'), case('three')])
    execute = f.service.execute
    calls = []
    def interrupt_second(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise KeyboardInterrupt()
        return execute(*args, **kwargs)
    monkeypatch.setattr(f.service, 'execute', interrupt_second)
    service = experiment(f, lambda *a, **k: answer(False))
    with pytest.raises(KeyboardInterrupt):
        service.run('example', path, issue=1)
    directory = next((f.service.root / 'results').glob('exp1_*'))
    result = service.result(directory)
    assert result['status'] == 'partial' and result['score'] is None
    assert [r['hit'] for r in result['issues'][0]['tests']] == [False, None]
    assert result['issues'][0]['stop_reason'] == 'interrupted'
    assert result['issues'][0]['unexecuted_case_ids'] == ['three']
    assert not json.loads((directory / 'plan.json').read_text())['execution_complete']
    service.ask = lambda *a, **k: pytest.fail('Reuse completed oracle call')
    assert service.match(directory)['score'] is None
    assert len(calls) == 2


@pytest.mark.parametrize('mode', ['case_rounds', None])
def test_saved_v1_experiments_keep_original_metric_units(prepared, mode):
    f = prepared
    path = collection(f.service.root / 'input.json', [case('one')])
    service = experiment(f, lambda *a, **k: answer())
    result = service.run('example', path, issue=1)
    directory = Path(result['directory'])
    plan = json.loads((directory / 'plan.json').read_text())
    plan['schema'] = 'abb.exp1.v1'
    plan['issues'][0]['cases'] = [case('one'), case('one')]
    execution = json.loads((directory / 'issue_1/execution.json').read_text())
    if mode:
        plan['execution_mode'] = mode
        run = execution['repetitions'][0]
        execution['repetitions'] = [dict(run, round_index=1), dict(run, round_index=1, source_case_index=1)]
    else:
        plan.pop('execution_mode')
        plan['issues'][0]['cases'] = [case('one')]
        execution = execution['repetitions'][0]
    write_json(directory / 'plan.json', plan)
    write_json(directory / 'issue_1/execution.json', execution)
    matched = service.match(directory)
    assert matched['schema'] == 'abb.exp1.v1'
    assert 'metrics_unit' not in matched
    assert matched['metrics']['Detection@1']['value'] == 1
    assert matched['issues'][0]['submitted_rounds'] == 1
    if mode:
        assert len(matched['issues'][0]['tests']) == 2
        assert matched['issues'][0]['hit_count'] == 1


def saved_result(agent, issue, hits, budget=5):
    return {'schema': SCHEMA, 'metrics_unit': 'case_executions', 'agent_id': agent,
            'experiment_id': agent + issue, 'directory': '/' + agent + issue,
            'budget': budget, 'status': 'completed',
            'issues': [{'issue_id': issue, 'tests': [{'hit': hit} for hit in hits]}]}


def test_aggregate_preserves_denominator_budgets_and_distinct_issue_identity():
    a = saved_result('a', 'issue_1', [False, True])
    b = saved_result('b', 'issue_1', [False] * 5)
    result = aggregate([a, b])
    assert result['issue_count'] == 2
    assert result['metrics']['Detection@1']['value'] == 0
    assert result['metrics']['Detection@5']['value'] == .5
    with pytest.raises(ValueError, match='Duplicate Issue'):
        aggregate([a, a])
    with pytest.raises(ValueError, match='legacy'):
        aggregate([a, {**b, 'schema': 'abb.exp1.v1'}])
    b['budget'] = 2
    b['issues'][0]['tests'] = [{'hit': False}, {'hit': None}]
    result = aggregate([a, b])
    assert result['issue_count'] == 2 and result['budget'] == 2
    assert result['metrics']['Detection@5']['status'] == 'outside_budget'
    b['issues'][0]['tests'][0]['hit'] = None
    assert aggregate([a, b])['metrics']['Detection@1']['value'] is None


def test_cli_aggregates_explicit_results_without_credentials(tmp_path, capsys, monkeypatch):
    from agentbench.cli.main import cli
    for name, value in [('a', saved_result('a', 'issue_1', [True])),
                        ('b', saved_result('b', 'issue_1', [False] * 5))]:
        write_json(tmp_path / name / 'result.json', value)
    monkeypatch.setattr('agentbench.cli.environment.load_execution_environment',
                        lambda *a: pytest.fail('Read-only results need no credentials'))
    assert cli(['exp1', 'result', '--experiment', str(tmp_path / 'a'), '--experiment', str(tmp_path / 'b')]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['metrics']['Detection@1']['value'] == .5


def test_cli_runs_ordered_cases_and_returns_full_matched_prompt(prepared, capsys, monkeypatch):
    from agentbench.cli.main import cli
    f = prepared
    path = collection(f.service.root / 'input.json', [case('hit'), case('never')])
    monkeypatch.setattr('agentbench.experiments.exp1.EvaluationService', lambda *a, **k: f.service)
    monkeypatch.setattr('agentbench.cli.environment.load_execution_environment',
                        lambda *a: SimpleNamespace(environ={}))
    monkeypatch.setattr(detection, 'ask_once', lambda *a, **k: answer())
    assert cli(['exp1', 'run', 'example', '--issue', '1', '--cases', str(path),
                '--root', str(f.service.root)]) == 0
    output = capsys.readouterr()
    result = json.loads(output.out)
    assert result['score'] == 1 and result['matched_case'] == case('hit')
    assert result['first_hit'] == 1 and len(f.agent.requests) == 1
    assert '[1/2] hit: 1' in output.err
    assert Path(result['matched_case_path']).is_file()


def test_unsupported_historical_target_never_falls_back(prepared, monkeypatch):
    f = prepared
    path = collection(f.service.root / 'input.json', [case('a')])
    def unsupported(*args, **kwargs):
        raise ValueError('Install Agent needs a historical source recipe')
    monkeypatch.setattr(f.service, 'prepare', unsupported)
    monkeypatch.setattr(f.service, 'execute', lambda *a, **k: pytest.fail('Must not use default version'))
    with pytest.raises(ValueError, match='historical source'):
        experiment(f, lambda *a, **k: pytest.fail('Must not assess')).run('example', path, issue=1)
