"""Generated candidates retry per original slot with a finite budget."""
from agentbench.sdk.common.artifacts import Artifacts
from agentbench.sdk.plugin.kuma.generation import generate_collection
from tests.test_case_preparation import generator


def test_invalid_candidate_retries_only_its_slot(tmp_path):
    from kuma.errors import ServiceError
    calls = []
    create, options = generator(tmp_path / 'repo', failures={1: ServiceError(
        'Invalid candidate', code='model_invalid_result', retryable=False)}, calls=calls)
    collection = generate_collection(create, count=3, options=options,
        files=Artifacts(tmp_path / 'evaluation'), repo=tmp_path / 'repo', allow_partial=True,
        max_attempts=5, retry_wait=lambda _: None)
    assert [entry['case_index'] for entry in collection['cases']] == [0, 1, 2]
    assert calls == [0, 1, 2, 3]
    assert collection['failures'] == []
    assert len(collection['attempt_failures']) == 1
    assert collection['attempt_failures'][0]['case_index'] == 1
    assert collection['attempt_failures'][0]['attempt_number'] == 1


def test_five_total_attempts_then_stop_current_generation(tmp_path):
    from kuma.errors import ServiceError
    calls = []
    def create(**kwargs):
        calls.append(True)
        raise ServiceError('Invalid candidate', code='model_output_policy_conflict')
    collection = generate_collection(create, count=3, options={},
        files=Artifacts(tmp_path / 'evaluation'), repo=tmp_path, allow_partial=True,
        max_attempts=5, retry_wait=lambda _: None)
    assert len(calls) == 5
    assert collection['failures'][0]['attempt_number'] == 5
    assert collection['unattempted_indices'] == [1, 2]


def test_unknown_request_is_not_reissued(tmp_path):
    from kuma.errors import ServiceError
    calls = []
    def create(**kwargs):
        calls.append(True)
        raise ServiceError('Connection lost after dispatch', code='network_error', retryable=True)
    collection = generate_collection(create, count=1, options={},
        files=Artifacts(tmp_path / 'evaluation'), repo=tmp_path, allow_partial=True,
        max_attempts=5, retry_wait=lambda _: None)
    assert len(calls) == 1
    assert collection['failures'][0]['code'] == 'network_error'
