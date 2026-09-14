"""Issue #7: batch generation uses only real SDK Case save/reuse APIs."""
import json

import pytest

from agentbench.sdk.common.artifacts import Artifacts
from agentbench.sdk.plugin.kuma.generation import generate_collection
from tests.sdk_fixtures.issue_run import profile


def test_two_cases_save_then_reuse_without_casegen(tmp_path):
    from kuma import create_run
    count = []
    repo = tmp_path/'repo'
    def cases(ctx):
        count.append(1)
        return {'case_id': f'case-{len(count)}', 'input_type': 'text',
                'inputs': [{'input_id': 'one', 'payload_type': 'text', 'payload': f'Message {len(count)}'}]}
    options = dict(repo_path=repo, agent_profile_path=profile(repo), case_provider=cases,
                   judge=False, allow_local=True, track_files=False, max_steps=1)
    collection = generate_collection(create_run, count=2, options=options,
                                     files=Artifacts(tmp_path/'output'), repo=repo)
    for entry in collection['cases']:
        run = create_run(repo_path=repo, case_path=entry['artifact'], judge=False, allow_local=True, track_files=False)
        assert run.case_id == entry['case_id']
        run.cancel()
    assert len(count) == 2
    assert len(list((tmp_path/'output/cases').glob('*.json'))) == 2


def test_mid_batch_failure_retains_preceding_cases(tmp_path):
    from kuma import create_run
    repo = tmp_path/'repo'
    calls = []
    def cases(ctx):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError('second Case failed')
        return {'case_id': 'saved', 'input_type': 'text',
                'inputs': [{'input_id': 'one', 'payload_type': 'text', 'payload': 'first'}]}
    with pytest.raises(Exception, match='custom Case Provider failed'):
        generate_collection(create_run, count=2, repo=repo, files=Artifacts(tmp_path/'output'),
            options=dict(repo_path=repo, agent_profile_path=profile(repo), case_provider=cases,
                         judge=False, allow_local=True, track_files=False, max_steps=1))
    collection = json.loads((tmp_path/'output/case-collection.json').read_text())
    assert len(collection['cases']) == 1 and collection['requested_count'] == 2
    assert (tmp_path/'output/cases/abb-case-0001.json').is_file()
