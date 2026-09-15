"""Partial Case preparation keeps stable slots and reusable official SDK files."""
import json
from types import SimpleNamespace

import pytest

from agentbench.sdk.common.artifacts import Artifacts
from agentbench.sdk.contracts import PreparedCase, PreparedCaseBatch, PreparationFailure
from agentbench.sdk.plugin.kuma.benchmark import KumaContainerRunner
from agentbench.sdk.plugin.kuma.generation import generate_collection, validate_collection
from tests.sdk_fixtures.issue_run import profile


@pytest.fixture
def registration(tmp_path):
    root = tmp_path / 'agent'
    (root / 'evaluation').mkdir(parents=True)
    (root / 'requirement.md').write_text('An offline test Agent')
    (root / 'evaluation/input-contract.json').write_text('{"encoding":"identity"}')
    return SimpleNamespace(path=root, case_count=5, agent_id='test-agent')


def generator(repo, *, failures=None, calls=None):
    """Real pinned PyPI save_case implementation with explicit offline Cases."""
    from kuma import create_run
    calls = calls if calls is not None else []
    source = profile(repo)

    def create(**options):
        slot = len(calls)
        calls.append(slot)
        if slot in (failures or {}):
            raise failures[slot]
        return create_run(**options)

    def case_provider(context):
        slot = calls[-1]
        return {'case_id': f'case-{slot}', 'input_type': 'text', 'inputs': [
            {'input_id': 'one', 'payload_type': 'text', 'payload': f'question-{slot}'}]}

    options = dict(repo_path=repo, agent_profile_path=source, case_provider=case_provider,
                   judge=False, allow_local=True, track_files=False, max_steps=1)
    return create, options


def install_worker(monkeypatch, tmp_path, *, failures=None, calls=None):
    requests = []

    def evaluate(agent, **kwargs):
        directory = tmp_path / f'output-{len(requests)}'
        files = Artifacts(directory, environ={})
        files.save('run.json', {'status': 'running', 'agent_id': agent.agent_id})
        kwargs['on_artifacts_ready'](directory)
        create, options = generator(directory / 'repo', failures=failures, calls=calls)
        requests.append(kwargs)
        collection = generate_collection(
            create, count=kwargs['generation_count'], options=options,
            files=Artifacts(directory / 'evaluation', environ={}), repo=directory / 'repo',
            case_indices=kwargs['generation_indices'], allow_partial=kwargs['partial_generation'])
        files.save('run.json', {'status': 'failed' if collection['failures'] else 'succeeded'})
        return directory

    monkeypatch.setattr('agentbench.sdk.plugin.kuma.benchmark.evaluate', evaluate)
    return requests


def test_third_of_five_failure_preserves_other_cases_and_public_diagnostics(
    registration, tmp_path, monkeypatch,
):
    from kuma.errors import ServiceError
    error = ServiceError('Invalid generated result', code='model_invalid_result', retryable=True,
                         request_id='server-request')
    error.client_request_id = 'logical-request'
    calls = []
    requests = install_worker(monkeypatch, tmp_path, failures={2: error}, calls=calls)
    runner = KumaContainerRunner(environ={'KUMA_API_KEY': 'offline'})
    batch = runner.prepare_case_batch(registration)
    assert [case.case_index for case in batch.cases] == [0, 1, 3, 4]
    assert calls == [0, 1, 2, 3, 4]  # No retry of the rejected slot.
    assert not batch.unattempted_indices
    failure = batch.failures_by_index[2]
    assert (failure.code, failure.retryable, failure.client_request_id, failure.request_id) == (
        'model_invalid_result', True, 'logical-request', 'server-request')
    assert failure.phase == 'case_generation'
    before = {case.case_index: case.artifact_path.read_bytes() for case in batch.cases}
    # Only the missing original slot is regenerated, not a new index zero.
    replacement = runner.prepare_case_batch(registration, case_indices=(2,))
    assert [case.case_index for case in replacement.cases] == [2]
    assert requests[-1]['generation_count'] == 5
    assert requests[-1]['generation_indices'] == (2,)
    assert calls == [0, 1, 2, 3, 4, 5]
    assert before == {case.case_index: case.artifact_path.read_bytes() for case in batch.cases}
    assert all(case.artifact_path.stat().st_mode & 0o222 == 0 for case in batch.cases)


@pytest.mark.parametrize('code', ['quota_exhausted', 'invalid_api_key', 'service_busy'])
def test_shared_generation_block_preserves_success_and_leaves_remaining_unattempted(
    registration, tmp_path, monkeypatch, code,
):
    from kuma.errors import ServiceError
    calls = []
    install_worker(monkeypatch, tmp_path, failures={1: ServiceError('Blocked', code=code)}, calls=calls)
    batch = KumaContainerRunner(environ={'KUMA_API_KEY': 'offline'}).prepare_case_batch(registration)
    assert [case.case_index for case in batch.cases] == [0]
    assert list(batch.failures_by_index) == [1]
    assert batch.unattempted_indices == (2, 3, 4)
    assert calls == [0, 1]


def test_explicit_subset_uses_saved_slot_numbers(registration, tmp_path, monkeypatch):
    install_worker(monkeypatch, tmp_path)
    batch = KumaContainerRunner(environ={'KUMA_API_KEY': 'offline'}).prepare_case_batch(
        registration, case_indices=(4, 1))
    assert [case.case_index for case in batch.cases] == [1, 4]
    assert [case.artifact_path.name for case in batch.cases] == ['case-0002.json', 'case-0005.json']


def test_partial_export_cannot_bypass_strict_collection_import(registration, tmp_path, monkeypatch):
    install_worker(monkeypatch, tmp_path, failures={2: RuntimeError('failed')})
    KumaContainerRunner(environ={'KUMA_API_KEY': 'offline'}).prepare_case_batch(registration)
    source = tmp_path / 'output-0/evaluation/case-collection.json'
    with pytest.raises(ValueError, match='unexpected Case count'):
        validate_collection(json.loads(source.read_text()), count=5)
    runner = KumaContainerRunner(environ={'KUMA_API_KEY': 'offline'}, options={
        'output': tmp_path / 'imported', 'case_collection': source})
    with pytest.raises(ValueError, match='unexpected Case count'):
        runner.prepare_case_batch(registration, case_indices=(0,))


def test_container_interruption_keeps_active_slot_distinct_from_unattempted(
    registration, tmp_path, monkeypatch,
):
    directory = tmp_path / 'interrupted'
    files = Artifacts(directory, environ={})
    files.save('run.json', {'status': 'failed'})
    files.save('evaluation/case-collection.json', {
        'schema': 'abb.case_collection.v2', 'requested_count': 5, 'cases': [],
        'active_case_index': 2, 'failures': [], 'unattempted_indices': [2, 4]})

    def evaluate(agent, **kwargs):
        kwargs['on_artifacts_ready'](directory)
        raise TimeoutError('Worker stopped')

    monkeypatch.setattr('agentbench.sdk.plugin.kuma.benchmark.evaluate', evaluate)
    batch = KumaContainerRunner(environ={'KUMA_API_KEY': 'offline'}).prepare_case_batch(
        registration, case_indices=(2, 4))
    assert batch.failures_by_index[2].code == 'request_state_unknown'
    assert batch.failures_by_index[2].artifacts['recovery'] == {
        'action': 'inspect_request', 'automatic': False, 'allow_replay': False,
        'phase': 'case_generation', 'client_request_id': None,
        'reason': 'Inspect the original Case generation request before creating new paid work'}
    assert batch.unattempted_indices == (4,)


def test_damaged_saved_case_isolated_and_never_marked_prepared(registration, tmp_path, monkeypatch):
    install_worker(monkeypatch, tmp_path)
    from agentbench.sdk.plugin.kuma import benchmark
    worker = benchmark.evaluate

    def evaluate(agent, **kwargs):
        directory = worker(agent, **kwargs)
        path = directory / 'evaluation/cases/abb-case-0002.json'
        artifact = json.loads(path.read_text())
        artifact['case']['inputs'][0]['payload'] = 'tampered'
        path.write_text(json.dumps(artifact))
        return directory

    monkeypatch.setattr(benchmark, 'evaluate', evaluate)
    batch = KumaContainerRunner(environ={'KUMA_API_KEY': 'offline'}).prepare_case_batch(registration)
    assert [case.case_index for case in batch.cases] == [0, 2, 3, 4]
    assert 'content does not match' in batch.failures_by_index[1].error_message


@pytest.mark.parametrize('status,expected,allow', [
    ('running', 'inspect_request', False), ('failed', 'generate_case', True),
])
def test_original_casegen_disposition_controls_explicit_regeneration(
    registration, tmp_path, monkeypatch, status, expected, allow,
):
    from kuma.errors import ServiceError
    error = ServiceError('Case request did not return', code='operation_wait_timeout', retryable=True)
    error.client_request_id = 'kreq_' + 'a' * 32
    monkeypatch.setattr('agentbench.sdk.plugin.kuma.request_recovery.inspect_requests',
                        lambda *a: {'status': status, 'request_type': 'case_generation',
                                    'client_request_id': error.client_request_id})
    install_worker(monkeypatch, tmp_path, failures={0: error})
    batch = KumaContainerRunner(environ={'KUMA_API_KEY': 'offline'}).prepare_case_batch(
        registration, case_indices=(2,))
    decision = batch.failures_by_index[2].artifacts['recovery']
    assert decision['action'] == expected and decision['allow_replay'] is allow


@pytest.mark.parametrize('indices', [(1, 1), (-1,), (5,), (True,)])
def test_invalid_slots_never_start_generation(registration, monkeypatch, indices):
    monkeypatch.setattr('agentbench.sdk.plugin.kuma.benchmark.evaluate',
                        lambda *args, **kwargs: pytest.fail('Invalid slots cannot invoke SDK'))
    with pytest.raises(ValueError):
        KumaContainerRunner(environ={'KUMA_API_KEY': 'offline'}).prepare_case_batch(
            registration, case_indices=indices)


def test_batch_contract_rejects_overlapping_states():
    with pytest.raises(ValueError, match='disjoint'):
        PreparedCaseBatch((PreparedCase(2),), (PreparationFailure(2, 'RuntimeError', 'failed'),))
    with pytest.raises(ValueError, match='disjoint'):
        PreparedCaseBatch((), unattempted_indices=(1, 1))
