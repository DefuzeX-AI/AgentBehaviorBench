"""Issue detection is scored from execution evidence, independently of Judges."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentbench.experiments.exp1 import Experiment1
from agentbench.experiments.exp1_inputs import load_cases
from agentbench.experiments.exp1_metrics import summarize
from agentbench.harness.ground_truth import detection
from agentbench.harness.ground_truth.issues import load_issue
from tests.test_ground_truth import reference_attempt, write_json
from tests.test_evaluation_service import project  # shared real scheduler / in-process target fixture
from tests.test_sdk_defaults import inprocess_worker_permissions


def case(identity):
    return {'case_id': identity, 'inputs': [{'input_id': 'task', 'payload': identity}]}


def install_issue(service, number=1):
    unit = service.root / 'unit'
    folder = unit / 'ground_truth' / f'issue_{number}'
    write_json(folder / 'verify.case.json', {
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


def test_all_source_cases_loaded_in_numeric_order_without_round_limit(tmp_path):
    folder = tmp_path / 'issue_1'
    for name in ('10', '2', '1'):
        write_json(folder / f'{name}.json', case(name))
    group = load_cases(tmp_path, 1)[0]
    assert [c['case_id'] for c in group['cases']] == ['1', '2', '10']
    assert group['available_cases'] == 3
    write_json(folder / '01.json', case('extra'))
    with pytest.raises(ValueError, match='duplicate'):
        load_cases(tmp_path, 10)


@pytest.mark.parametrize('budget', [0, 51, -1, True])
def test_budget_limits(tmp_path, budget):
    with pytest.raises(ValueError, match='1 and 50'):
        load_cases(tmp_path, budget)


def test_collection_order_and_mixed_formats_rejected(tmp_path):
    folder = tmp_path / 'issue_1'
    write_json(folder / 'cases.json', {'schema': 'abb.cases.v1', 'cases': [case('z'), case('a')]})
    assert [c['case_id'] for c in load_cases(tmp_path, 50)[0]['cases']] == ['z', 'a']
    write_json(folder / '0001.json', case('b'))
    with pytest.raises(ValueError, match='OR'):
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
    case_dir = service.root / 'cases'
    write_json(case_dir / 'issue_1/0001.json', case('hello'))
    seen = []
    def ask(model, *, system, payload):
        assert 'finding_summary' not in payload
        assert payload['issue']['issue']['number'] == 1
        seen.append(payload)
        return answer()
    experiment = Experiment1(service.root, execution_service=service, ask=ask, output=lambda _: None)
    # The in-process Echo fixture has no model calls. Inject the existing trace
    # fixture for the oracle while exercising real Case scheduling/persistence.
    candidate = {k: v for k, v in load_issue(service.root, 'example', 'issue_1')['trajectories'][0].items()
                 if k != 'attempt'}
    monkeypatch.setattr('agentbench.experiments.exp1.read_candidate', lambda *a, **k: candidate)
    result = experiment.run('example', case_dir, tests=1)
    assert len(seen) == 1, result
    assert result['metrics']['Detection@1']['value'] == 1
    assert result['issues'][0]['execution_attempts'] == 1
    assert result['issues'][0]['hit_count'] == 1
    assert result['issues'][0]['first_hit'] == 1
    assert policies and set(policies) == {0}
    assert result['issues'][0]['tests'][0]['evidence']['candidate']
    assert len(agent.requests) == 1
    assert all(p.closed for p in processes)
    suite = service.result(result['issues'][0]['tests'][0]['suite'])
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
    (service.root / 'unit/ground_truth/issue_1/verify.case.json').unlink()
    assert experiment.match(result['directory'])['metrics'] == result['metrics']

    # Previously saved experiments used one Suite with one execution per Case.
    directory = Path(result['directory'])
    plan = json.loads((directory / 'plan.json').read_text())
    plan.pop('execution_mode')
    write_json(directory / 'plan.json', plan)
    execution = json.loads((directory / 'issue_1/execution.json').read_text())
    write_json(directory / 'issue_1/execution.json', execution['repetitions'][0])
    experiment.ask = lambda *a, **k: answer()
    legacy = experiment.match(directory)
    assert legacy['issues'][0]['tests'][0]['hit'] is True
    assert legacy['metrics'] == result['metrics']


def test_missing_suite_keeps_issue_in_denominator(project, oracle, monkeypatch):
    service, _, _ = project
    install_issue(service)
    folder = service.root / 'cases'
    write_json(folder / 'issue_1/0001.json', case('hello'))
    monkeypatch.setattr(service, 'execute', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('Infrastructure unavailable')))
    experiment = Experiment1(service.root, execution_service=service,
                             ask=lambda *a, **k: pytest.fail('No evidence'), output=lambda _: None)
    result = experiment.run('example', folder, tests=1)
    assert result['issue_count'] == 1 and result['status'] == 'partial'
    assert result['metrics']['Detection@1']['value'] is None
    assert result['metrics']['Detection@1']['bounds'] == [0, 1]
    assert result['issues'][0]['execution_attempts'] == 0


def test_reference_version_mismatch_blocks_before_execution(project, oracle, monkeypatch):
    service, _, _ = project
    folder = install_issue(service)
    path = folder / 'verify.case.json'
    doc = json.loads(path.read_text())
    write_json(path, {**doc, 'commit_version': 'wrong-version'})
    write_json(service.root / 'cases/issue_1/0001.json', case('hello'))
    monkeypatch.setattr(service, 'execute', lambda *a, **k: pytest.fail('Must preflight'))
    with pytest.raises(ValueError, match='revision'):
        Experiment1(service.root, execution_service=service).run('example', service.root / 'cases')


def test_each_issue_executes_its_prepared_revision(project, oracle, monkeypatch):
    service, _, _ = project
    revisions = ['a' * 40, 'b' * 40, 'a' * 40]
    for number, revision in enumerate(revisions, 1):
        folder = install_issue(service, number)
        path = folder / 'verify.case.json'
        write_json(path, {**json.loads(path.read_text()), 'commit_version': revision})
        write_json(service.root / f'cases/issue_{number}/0001.json', case(str(number)))
    prepared, executed = [], []
    def prepare(agent_id, revision, **kwargs):
        prepared.append(revision)
        return SimpleNamespace(revision=revision, describe=lambda: {'revision': revision})
    def execute(agent_id, cases, *, target, **kwargs):
        executed.append((cases[0]['case_id'], target.revision))
        raise RuntimeError('Stop after recording target selection')
    monkeypatch.setattr(service, 'prepare', prepare)
    monkeypatch.setattr(service, 'execute', execute)
    experiment = Experiment1(service.root, execution_service=service, output=lambda _: None)
    result = experiment.run('example', service.root / 'cases', tests=2)
    assert prepared == revisions[:2]
    assert executed == [(str(n), r) for n, r in enumerate(revisions, 1) for _ in range(2)]
    plan = json.loads((Path(result['directory']) / 'plan.json').read_text())
    assert plan['prepared_targets']['issue_2']['revision'] == revisions[1]


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


def test_issue_workers_repeat_each_case_and_continue_after_failures(project, oracle, monkeypatch):
    from threading import Barrier, Lock
    service, _, _ = project
    barrier, lock, calls = Barrier(2), Lock(), []
    for number in (1, 2):
        install_issue(service, number)
        write_json(service.root / f'cases/issue_{number}/cases.json', {
            'schema': 'abb.cases.v1', 'cases': [case(str(number))]})
    def execute(agent, cases, **kwargs):
        assert kwargs.get('judge') is None
        assert kwargs['concurrency'].max_parallel_cases == 1
        assert kwargs['retry_policy'].max_retries == 0
        with lock:
            calls.append([c['case_id'] for c in cases])
        barrier.wait(timeout=5)
        raise RuntimeError('Synthetic execution failure after submission')
    monkeypatch.setattr(service, 'execute', execute)
    result = Experiment1(service.root, execution_service=service, output=lambda _: None).run(
        'example', service.root / 'cases', tests=3, workers=2)
    assert sorted(calls) == [['1']] * 3 + [['2']] * 3
    assert all(len(i['tests']) == 3 for i in result['issues'])
    assert all(t['execution_wall_seconds'] >= 0 and t['execution_state'] == 'failed'
               for i in result['issues'] for t in i['tests'])
    assert result['issue_count'] == 2
    assert all(i['submitted_tests'] == 3 for i in result['issues'])


def test_cli_result_is_read_only_and_needs_no_credentials(tmp_path, capsys, monkeypatch):
    from agentbench.cli.main import cli
    write_json(tmp_path / 'result.json', {'schema': 'abb.exp1.v1', 'status': 'completed'})
    monkeypatch.setattr('agentbench.cli.environment.load_execution_environment',
                        lambda *a, **k: pytest.fail('Read-only result must not load credentials'))
    assert cli(['exp1', 'result', '--experiment', str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'completed'


@pytest.mark.parametrize(('case_count', 'round_count'), [(1, 10), (3, 2)])
def test_rounds_have_fresh_sessions_workspaces_and_timings(project, oracle, monkeypatch, case_count, round_count):
    from agentbench.sdk.integration import execution
    service, agent, processes = project
    manifest = service.root / 'unit/agent.toml'
    with manifest.open('a') as stream:
        stream.write('[evaluation.workspace]\npath="/home/agent/work"\ninitial_state="empty"\n')
    install_issue(service)
    source = {'case_id': 'same', 'inputs': [
        {'input_id': 'first', 'payload': 'one'}, {'input_id': 'second', 'payload': 'two'}]}
    for i in range(case_count):
        write_json(service.root / f'cases/issue_1/{i+1:04d}.json', {**source, 'case_id': f'same-{i}'})
    total = case_count * round_count
    workspaces = []
    prepare = execution.prepare_workspace
    def inspect_workspace(root, destination, policy):
        assert not list(destination.iterdir())
        workspaces.append(destination)
        contract = prepare(root, destination, policy)
        (destination / 'left-by-previous-run.txt').write_text('marker')
        return contract
    monkeypatch.setattr(execution, 'prepare_workspace', inspect_workspace)
    candidate = {k: v for k, v in load_issue(service.root, 'example', 'issue_1')['trajectories'][0].items()
                 if k != 'attempt'}
    monkeypatch.setattr('agentbench.experiments.exp1.read_candidate', lambda *a, **k: candidate)
    experiment = Experiment1(service.root, execution_service=service, ask=lambda *a, **k: answer(), output=lambda _: None)
    result = experiment.run('example', service.root / 'cases', tests=round_count)
    rows = result['issues'][0]['tests']
    assert len(rows) == total
    assert [r['case_id'] for r in rows] == [f'same-{i}' for i in range(case_count)] * round_count
    assert [r['round_index'] for r in rows] == [i for i in range(1, round_count+1) for _ in range(case_count)]
    assert len({r['suite'] for r in rows}) == total
    assert all(r['execution_attempts'] == 1 and r['hit'] is True for r in rows)
    assert all(r['execution_wall_seconds'] > 0 for r in rows)
    assert [r['test_index'] for r in rows] == list(range(1, total+1))
    assert len(agent.requests) == total * 2
    pairs = [agent.requests[i:i+2] for i in range(0, total * 2, 2)]
    assert all(pair[0]['session_id'] == pair[1]['session_id'] for pair in pairs)
    assert len({pair[0]['session_id'] for pair in pairs}) == total
    assert [r['input'] for r in agent.requests] == ['one', 'two'] * total
    execution_workspaces = [p for p in workspaces if p.parent.name == "attempts"]
    assert len(execution_workspaces) == total
    assert len(set(workspaces)) == len(workspaces)
    assert all(not p.exists() for p in workspaces)
    assert all(p.closed for p in processes)
    assert result['metrics']['Detection@1']['value'] == 1
    assert len(result['issues'][0]['rounds']) == round_count
    assert all(r['case_count'] == case_count for r in result['issues'][0]['rounds'])
    if round_count == 10:
        assert result['metrics']['Detection@10']['value'] == 1
    for i in range(1, total+1):
        saved = Path(result['directory']) / 'issue_1/repetitions' / f'{i:04d}/execution.json'
        assert json.loads(saved.read_text())['wall_seconds'] == rows[i-1]['execution_wall_seconds']
    monkeypatch.setattr(service, 'execute', lambda *a, **k: pytest.fail('Matching must not rerun'))
    experiment.ask = lambda *a, **k: pytest.fail('Matching must reuse each repetition assessment')
    cached = experiment.match(result['directory'])['issues'][0]['tests']
    assert all(r['cache_reused'] for r in cached)
    assert [(r['suite'], r['execution_wall_seconds'], r['hit']) for r in cached] == [
        (r['suite'], r['execution_wall_seconds'], r['hit']) for r in rows]


def test_detection_counts_rounds_instead_of_individual_cases():
    from agentbench.experiments.exp1_metrics import summarize_rounds
    rows = [{'round_index': number, 'hit': hit, 'execution_wall_seconds': 1.5}
            for number, hits in [(1, [False, False]), (2, [None, False]), (3, [False, True])]
            for hit in hits]
    rounds = summarize_rounds(rows)
    assert [r['hit'] for r in rounds] == [False, None, True]
    assert all(r['case_count'] == 2 and r['execution_wall_seconds'] == 3 for r in rounds)
    assert summarize([{'tests': rounds}], 3)['Detection@1']['value'] == 0
