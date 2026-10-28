"""Issue detection is scored from execution evidence, independently of Judges."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentbench.experiments.exp1 import Experiment1
from agentbench.experiments.exp1_inputs import load_cases
from agentbench.experiments.exp1_metrics import summarize
from agentbench.harness.ground_truth import detection
from agentbench.harness.ground_truth.issues import discover_issues, load_issue
from tests.test_ground_truth import reference_attempt, write_json
from tests.test_evaluation_service import project  # shared real scheduler / in-process target fixture
from tests.test_sdk_defaults import inprocess_worker_permissions


def case(identity):
    return {'case_id': identity, 'inputs': [{'input_id': 'task', 'payload': identity}]}


def install_issue(service, number=1):
    unit = service.root / 'unit'
    folder = unit / 'ground_truth' / f'issue_{number}'
    write_json(folder / 'case.verified.json', {
        'issue': {'number': number, 'title': 'Secret reference title'},
        'expected': 'Echo the input.', 'defect': 'Adds a turn counter.',
        'Root cause': 'Fixture reference; never provided to target.'})
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
            'candidate_step_ids': [1], 'candidate_decisive_step': 1 if hit else None}


def inject_candidate(service, monkeypatch):
    # The in-process Echo fixture has no model calls. Inject the existing trace
    # fixture for the oracle while exercising real Case scheduling/persistence.
    candidate = {k: v for k, v in load_issue(service.root, 'example', 'issue_1')['trajectories'][0].items()
                 if k != 'attempt'}
    monkeypatch.setattr('agentbench.experiments.exp1.read_candidate', lambda *a, **k: candidate)


def test_case_order_budget_and_duplicate_identity(tmp_path):
    for name in ('10', '2', '1'):
        write_json(tmp_path / f'{name}.json', case(name))
    group = load_cases(tmp_path, 2)
    assert [c['case_id'] for c in group['cases']] == ['1', '2', '10']
    assert group['available_cases'] == 3
    write_json(tmp_path / '01.json', case('extra'))
    with pytest.raises(ValueError, match='Duplicate'):
        load_cases(tmp_path, 50)


@pytest.mark.parametrize('budget', [0, 51, -1, True])
def test_budget_limits(tmp_path, budget):
    with pytest.raises(ValueError, match='1 and 50'):
        load_cases(tmp_path, budget)


def test_collection_order_and_mixed_formats_rejected(tmp_path):
    write_json(tmp_path / 'cases.json', {'schema': 'abb.cases.v1', 'cases': [case('z'), case('a')]})
    assert [c['case_id'] for c in load_cases(tmp_path, 50)['cases']] == ['z', 'a']
    write_json(tmp_path / '0001.json', case('b'))
    with pytest.raises(ValueError, match='OR'):
        load_cases(tmp_path, 50)


def test_case_group_rejects_issue_folders(tmp_path):
    write_json(tmp_path / 'issue_1/0001.json', case('a'))
    with pytest.raises(ValueError, match='Unexpected folder'):
        load_cases(tmp_path, 50)


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
    path = folder / 'case.verified.json'
    doc = json.loads(path.read_text())
    doc['issue']['number'] = 2
    write_json(path, doc)
    with pytest.raises(ValueError, match='identity'):
        load_issue(service.root, 'example', 'issue_1')


def test_issue_discovery_skips_folders_without_verified_case(project):
    service, _, _ = project
    for number in (10, 2):
        install_issue(service, number)
    (service.root / 'unit/ground_truth/issue_3/runs').mkdir(parents=True)
    (service.root / 'unit/ground_truth/notes').mkdir()
    assert discover_issues(service.root, 'example') == ['issue_2', 'issue_10']


def test_execute_then_match_without_judge_and_without_rerunning(project, oracle, monkeypatch):
    from agentbench.harness.scheduling.retry import RetryPolicy
    policies = []
    permits = RetryPolicy.permits
    def check_policy(policy, *args):
        policies.append(policy.max_retries)
        return permits(policy, *args)
    monkeypatch.setattr(RetryPolicy, 'permits', check_policy)
    service, agent, processes = project
    install_issue(service)
    case_dir = service.root / 'cases/run-01'
    write_json(case_dir / '0001.json', case('hello'))
    write_json(case_dir / '0002.json', case('second'))
    seen = []
    def ask(model, *, system, payload):
        assert 'finding_summary' not in payload
        assert payload['issue']['issue']['number'] == 1
        seen.append(payload)
        return answer()
    experiment = Experiment1(service.root, execution_service=service, ask=ask, output=lambda _: None)
    inject_candidate(service, monkeypatch)
    result = experiment.run('example', case_dir, tests=1)
    assert len(seen) == 1, result
    assert result['metrics']['Detection@1']['value'] == 1
    assert result['cost']['execution_attempts'] == 2
    assert result['issues'][0]['hit_count'] == 1
    assert result['issues'][0]['first_hit'] == 1
    assert policies and set(policies) == {0}
    assert result['issues'][0]['tests'][0]['evidence']['candidate']
    assert len(agent.requests) == 2
    assert all(p.closed for p in processes)
    suite = service.result(result['rounds'][0]['suite'])
    assert suite['suite']['judge_counts'].get('issue', 0) == 0
    assert not list(Path(suite['directory']).rglob('report.json'))
    # The target sees exactly the submitted public payload, never hidden GT.
    assert 'Secret reference title' not in str(agent.requests)
    def forbidden(*args, **kwargs):
        pytest.fail('Matching must not execute a Case or repeat a completed oracle call')
    monkeypatch.setattr(service, 'execute', forbidden)
    experiment.ask = forbidden
    cached = experiment.match(result['directory'])
    assert cached['issues'][0]['tests'][0]['cache_reused']
    assert cached['metrics'] == result['metrics']
    # The evaluator uses its frozen GT snapshot, not a later edited live Issue.
    (service.root / 'unit/ground_truth/issue_1/case.verified.json').unlink()
    assert experiment.match(result['directory'])['metrics'] == result['metrics']

    # Existing v2 plans have one Suite and one execution per Case.
    directory = Path(result['directory'])
    plan = json.loads((directory / 'plan.json').read_text())
    plan.pop('execution_mode')
    write_json(directory / 'plan.json', plan)
    execution = json.loads((directory / 'execution.json').read_text())
    write_json(directory / 'execution.json', execution['rounds'][0])
    experiment.ask = lambda *a, **k: answer()
    legacy = experiment.match(directory)
    assert len(legacy['issues'][0]['tests']) == 2
    assert legacy['metrics'] == result['metrics']


def test_one_execution_is_matched_against_every_issue(project, oracle, monkeypatch):
    service, agent, _ = project
    for number in (1, 2):
        install_issue(service, number)
    (service.root / 'unit/ground_truth/issue_3').mkdir()
    case_dir = service.root / 'cases/run-01'
    write_json(case_dir / '0001.json', case('hello'))
    write_json(case_dir / '0002.json', case('second'))
    compared = []
    def ask(model, *, system, payload):
        number = payload['issue']['issue']['number']
        compared.append(number)
        return answer(number == 1)
    inject_candidate(service, monkeypatch)
    result = Experiment1(service.root, execution_service=service, ask=ask, output=lambda _: None).run(
        'example', case_dir, tests=2)
    assert len(agent.requests) == 4
    assert result['cost']['execution_attempts'] == 4
    # Both tests share one injected trajectory, so each Issue's second request reuses the first.
    assert sorted(compared) == [1, 2]
    assert [i['issue_id'] for i in result['issues']] == ['issue_1', 'issue_2']
    assert [i['hit_count'] for i in result['issues']] == [2, 0]
    assert [[t['cache_reused'] for t in i['tests']] for i in result['issues']] == [[False, True, True, True]] * 2
    assert result['metrics']['Detection@1']['value'] == .5
    assert result['status'] == 'completed'


def test_no_verified_issue_blocks_before_execution(project, oracle, monkeypatch):
    service, _, _ = project
    write_json(service.root / 'cases/run-01/0001.json', case('hello'))
    monkeypatch.setattr(service, 'execute', lambda *a, **k: pytest.fail('Must preflight'))
    with pytest.raises(ValueError, match='case.verified.json'):
        Experiment1(service.root, execution_service=service).run('example', service.root / 'cases/run-01')


def test_missing_suite_keeps_issue_in_denominator(project, oracle, monkeypatch):
    service, _, _ = project
    install_issue(service)
    folder = service.root / 'cases/run-01'
    write_json(folder / '0001.json', case('hello'))
    monkeypatch.setattr(service, 'execute', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('Infrastructure unavailable')))
    experiment = Experiment1(service.root, execution_service=service,
                             ask=lambda *a, **k: pytest.fail('No evidence'), output=lambda _: None)
    result = experiment.run('example', folder, tests=1)
    assert result['issue_count'] == 1 and result['status'] == 'partial'
    assert result['metrics']['Detection@1']['value'] is None
    assert result['metrics']['Detection@1']['bounds'] == [0, 1]
    assert result['cost']['execution_attempts'] == 0
    assert 'Infrastructure unavailable' in result['issues'][0]['tests'][0]['reason']


def test_reference_version_mismatch_blocks_before_execution(project, oracle, monkeypatch):
    service, _, _ = project
    folder = install_issue(service)
    path = folder / 'case.verified.json'
    doc = json.loads(path.read_text())
    write_json(path, {**doc, 'commit_version': 'wrong-version'})
    write_json(service.root / 'cases/run-01/0001.json', case('hello'))
    monkeypatch.setattr(service, 'execute', lambda *a, **k: pytest.fail('Must preflight'))
    with pytest.raises(ValueError, match='revision'):
        Experiment1(service.root, execution_service=service).run('example', service.root / 'cases/run-01')


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
    assert len(calls) == 1
    result = detection.assess(reference, candidate, ask=lambda *a, **k: answer(), retry_failed=True, **args)
    assert result['hit'] is True
    assert len(list((tmp_path / 'calls').rglob('*.json'))) == 2


def test_partial_negative_is_unknown_and_oversize_never_truncated(project, oracle, tmp_path):
    service, _, _ = project
    install_issue(service)
    reference = load_issue(service.root, 'example', 'issue_1')
    candidate = {**reference['trajectories'][0], 'status': 'partial'}
    result = detection.assess(reference, candidate, directory=tmp_path / 'calls', environ={}, model=oracle,
                              ask=lambda *a, **k: answer(False))
    assert result['hit'] is None
    with pytest.raises(ValueError, match='not truncated'):
        detection.assess(reference, candidate, directory=tmp_path / 'calls',
                          environ={'ABB_GT_MAX_BYTES': '10'}, model=oracle,
                          ask=lambda *a, **k: pytest.fail('Oversize'))


def test_openrouter_default_is_independent_of_judge_and_target(monkeypatch):
    seen = {}
    monkeypatch.setattr(detection, 'model_config', lambda env: seen.update(env))
    detection.oracle_model({'ABB_MODEL_PROVIDER': 'deepseek', 'ABB_MODEL': 'target',
                            'ABB_LOCAL_JUDGE_MODEL': 'legacy', 'ABB_GT_MODEL': 'legacy-gt',
                            'OPENROUTER_MODEL': 'default', 'OPENROUTER_API_KEY': 'test'})
    assert seen['ABB_MODEL_PROVIDER'] == 'openrouter'
    assert seen['OPENROUTER_MODEL'] == 'default'
    assert not {'ABB_MODEL', 'ABB_GT_MODEL', 'ABB_LOCAL_JUDGE_MODEL'} & seen.keys()


def test_cli_registration_and_default_budget():
    from agentbench.cli.main import build_parser
    args = build_parser().parse_args(['exp1', 'run', 'example', '--case-dir', 'cases'])
    assert args.tests == 50 and args.workers == 1
    assert not hasattr(args, 'judge') and not hasattr(args, 'view')
    with pytest.raises(SystemExit):
        build_parser().parse_args(['exp1', 'run', 'example'])


def test_case_workers_are_bounded_and_all_cases_repeat_each_round(project, oracle, monkeypatch):
    service, _, _ = project
    calls = []
    for number in (1, 2):
        install_issue(service, number)
    write_json(service.root / 'cases/run-01/cases.json', {
        'schema': 'abb.cases.v1', 'cases': [case(str(i)) for i in range(5)]})
    def execute(agent, cases, **kwargs):
        assert kwargs.get('judge') is None
        assert kwargs['concurrency'].max_parallel_cases == 2
        assert kwargs['retry_policy'].max_retries == 0
        calls.append([c['case_id'] for c in cases])
        raise RuntimeError('Synthetic execution failure after submission')
    monkeypatch.setattr(service, 'execute', execute)
    result = Experiment1(service.root, execution_service=service, output=lambda _: None).run(
        'example', service.root / 'cases/run-01', tests=3, workers=2)
    assert calls == [['0', '1', '2', '3', '4']] * 3
    assert result['issue_count'] == 2
    assert result['submitted_tests'] == 15
    assert result['submitted_rounds'] == 3
    assert all(len(i['tests']) == 15 and len(i['rounds']) == 3 for i in result['issues'])


def test_cli_result_is_read_only_and_needs_no_credentials(tmp_path, capsys, monkeypatch):
    from agentbench.cli.main import cli
    write_json(tmp_path / 'result.json', {'schema': 'abb.exp1.v2', 'status': 'completed'})
    monkeypatch.setattr('agentbench.cli.environment.load_execution_environment',
                        lambda *a, **k: pytest.fail('Read-only result must not load credentials'))
    assert cli(['exp1', 'result', '--experiment', str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'completed'


@pytest.mark.parametrize(('case_count', 'round_count'), [(1, 10), (3, 2)])
def test_all_cases_repeat_in_fresh_sessions_and_workspaces(project, oracle, monkeypatch, case_count, round_count):
    from agentbench.sdk.integration import execution
    service, agent, processes = project
    manifest = service.root / 'unit/agent.toml'
    with manifest.open('a') as stream:
        stream.write('[evaluation.workspace]\npath="/home/agent/work"\ninitial_state="empty"\n')
    install_issue(service)
    case_dir = service.root / 'cases/run-01'
    for i in range(case_count):
        write_json(case_dir / f'{i+1:04d}.json', {
            'case_id': f'case-{i}', 'inputs': [
                {'input_id': 'task', 'payload': f'{i}-one'}]})
    workspaces = []
    prepare = execution.prepare_workspace
    def inspect_workspace(root, destination, policy):
        assert not list(destination.iterdir())
        workspaces.append(destination)
        return prepare(root, destination, policy)
    monkeypatch.setattr(execution, 'prepare_workspace', inspect_workspace)
    inject_candidate(service, monkeypatch)
    experiment = Experiment1(service.root, execution_service=service,
                             ask=lambda *a, **k: answer(), output=lambda _: None)
    result = experiment.run('example', case_dir, tests=round_count)
    assert result['submitted_rounds'] == round_count and result['submitted_tests'] == case_count * round_count
    assert len(result['rounds']) == round_count
    assert len({r['suite'] for r in result['rounds']}) == round_count
    assert all(r['wall_seconds'] > 0 for r in result['rounds'])
    assert [r['round_index'] for r in result['tests']] == [round_index for round_index in range(1, round_count + 1) for _ in range(case_count)]
    assert [r['case_id'] for r in result['tests']] == [f'case-{i}' for i in range(case_count)] * round_count
    assert all(r['execution_attempts'] == 1 and r['execution_wall_seconds'] is not None
               for r in result['tests'])
    assert len(agent.requests) == case_count * round_count
    assert len({r['session_id'] for r in agent.requests}) == case_count * round_count
    assert len({p for p in workspaces if p.parent.name == 'attempts'}) == case_count * round_count
    assert all(not p.exists() for p in workspaces)
    assert all(p.closed for p in processes)
    assert result['issues'][0]['first_hit'] == 1
    assert len(result['issues'][0]['rounds']) == round_count
    assert result['metrics']['Detection@1']['value'] == 1
    for i in range(1, round_count + 1):
        saved = Path(result['directory']) / 'execution/rounds' / f'{i:04d}/execution.json'
        assert json.loads(saved.read_text())['wall_seconds'] == result['rounds'][i-1]['wall_seconds']
    monkeypatch.setattr(service, 'execute', lambda *a, **k: pytest.fail('Match must not execute'))
    experiment.ask = lambda *a, **k: pytest.fail('Match must reuse oracle result')
    assert experiment.match(result['directory'])['metrics'] == result['metrics']


def test_detection_counts_rounds_not_individual_cases():
    from agentbench.experiments.exp1_metrics import summarize_rounds
    rows = [{'round_index': number, 'hit': hit}
            for number, hits in [(1, [False, False]), (2, [None, False]), (3, [False, True])]
            for hit in hits]
    rounds = summarize_rounds(rows)
    assert [r['hit'] for r in rounds] == [False, None, True]
    assert all(r['case_count'] == 2 for r in rounds)
    assert summarize([{'tests': rounds}], 3)['Detection@1']['value'] == 0
