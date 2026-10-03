"""Incorrect source/input adaptations cannot pass merely by compiling."""
import copy

import pytest

from agentbench.onboarding.build_agent_env.common.errors import BuildError
from tests.agent_build_fixtures import source, plan, Client, FILES, build


class ReviewedClient(Client):
    def __init__(self, plan, *, reject_always=False):
        super().__init__(plan)
        self.reject_always = reject_always

    def generate(self, payload, **kwargs):
        response = super().generate(payload, **kwargs)
        if payload.get('response_kind') == 'configuration_review' and payload['target_path'] == 'bindings/bridge.py':
            binding_reviews = [p for p in self.reviews if p['target_path'] == 'bindings/bridge.py']
            if self.reject_always or len(binding_reviews) == 1:
                response['issues'] = ['Native graph requires a mapping; parse the SDK text before invoking it.']
        return response


def test_rejected_candidate_is_corrected_before_install_and_review_is_cached(source, plan):
    client = ReviewedClient(plan)
    assert build(source, plan, client=client).status == 'generated'
    requests = [p for p in client.requests if p.get('target_path') == 'bindings/bridge.py']
    assert len(requests) == 2
    assert 'parse the SDK text' in requests[1]['validation_error']
    assert requests[1]['previous_response']['content'] == FILES['bindings/bridge.py']
    review = next(p for p in client.reviews if p['target_path'] == 'bindings/bridge.py')
    assert review['proposed_content'] == FILES['bindings/bridge.py']
    assert review['sdk_requirements'] and review['context']['files']
    assert 'agent.toml' in review['completed_files']
    resumed = Client(plan)
    assert build(source, plan, client=resumed).status == 'generated'
    assert resumed.requests == resumed.reviews == []


def test_exhausted_review_preserves_prior_files_and_never_registers(source, plan):
    with pytest.raises(BuildError, match='Source compatibility review'):
        build(source, plan, client=ReviewedClient(plan, reject_always=True))
    assert (source.directory / 'agent.toml').is_file()
    assert not (source.directory / 'bindings/bridge.py').exists()
    assert not (source.directory / 'Dockerfile').exists()
    assert not (source.directory.parents[1] / 'registry.toml').exists()


def test_changed_existing_file_is_reviewed_and_preserved_as_conflict(source, plan):
    build(source, plan)
    binding = source.directory / 'bindings/bridge.py'
    changed = '# Edited by maintainer\n' + binding.read_text(encoding='utf-8')
    binding.write_text(changed, encoding='utf-8')
    client = ReviewedClient(plan, reject_always=True)
    result = build(source, plan, client=client)
    assert result.status == 'conflict'
    assert 'Source compatibility review' in result.messages[0]
    assert binding.read_text(encoding='utf-8') == changed
    assert client.requests == []


def test_secret_review_response_is_never_recorded(source, plan):
    secret = 'private-review-secret-987654321'
    class SecretClient(Client):
        def generate(self, payload, **kwargs):
            result = copy.deepcopy(super().generate(payload, **kwargs))
            if payload.get('response_kind') == 'configuration_review':
                result['summary'] = secret
            return result
    with pytest.raises(BuildError, match='Review response contains a credential'):
        build(source, plan, client=SecretClient(plan), environ={'TOKEN': secret})
    assert not (source.directory / 'agent.toml').exists()
    assert not any(secret in p.read_text(encoding='utf-8')
                   for p in (source.directory.parents[2] / 'cache').rglob('*.json'))


def test_changing_generation_model_replans_and_reviews_existing_files(source, plan):
    build(source, plan, model='provider/small')
    client = Client(plan)
    assert build(source, plan, client=client, model='provider/large').status == 'generated'
    assert [request.get('target_path') for request in client.requests] == [None]
    assert {request['target_path'] for request in client.reviews} == set(FILES) - {'.dockerignore'}
