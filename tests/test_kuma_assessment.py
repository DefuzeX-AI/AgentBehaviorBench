"""Claim evidence reaches the real SDK without inventing complete capture."""
import asyncio
import hashlib
import json

import pytest

from agentbench.observe.result import sanitize_result
from agentbench.sdk.plugin.kuma.assessment import public_message_bundle, submission_options
from agentbench.sdk.plugin.kuma.runner import drive_run
from tests.sdk_fixtures.issue_run import sdk_run


@pytest.mark.parametrize('output,attributed', [
    ('answer', True), (0, True), (False, True), ({'answer': 1}, True),
    ('', False), ('  ', False), (None, False), ([], False), ({}, False),
])
def test_output_attribution_does_not_invent_public_messages(output, attributed):
    options = submission_options({'status': 'succeeded', 'output': output})
    assert ('agent_output_actor' in options) == attributed
    assert options['public_messages']['public_messages'] == []
    assert options['public_messages']['coverage']['public_messages'] != 'complete'
    assert options['public_messages']['coverage']['reasons'] == ['source_incomplete']


def test_internal_graph_state_is_not_reclassified_as_public_text():
    result = {'status': 'succeeded', 'output': 'final', 'raw_output': {'state': {
        'messages': [{'type': 'ai', 'content': 'internal reasoning or older turn'}]}}}
    assert public_message_bundle(result)['public_messages'] == []


def test_native_judge_preserves_coverage_limitations_and_uses_durable_root(tmp_path, monkeypatch):
    from agentbench.sdk.plugin.kuma import native_judge
    from tests.test_kuma_deferred_judge import offline_assessment
    assessment = offline_assessment()
    notice = 'Claim review is unavailable for this fixture.'
    class Provider:
        def __init__(self, client, *, state_root):
            assert state_root.is_dir()
        def judge(self, context):
            return {'status': 'pass', 'issues': [], 'extensions': {
                'assessment': assessment, 'claim_coverage_notice': notice}}
    monkeypatch.setattr(native_judge, 'context_from_request', lambda *args: object())
    monkeypatch.setattr('kuma.providers.OfficialJudgeProvider', Provider)
    monkeypatch.setattr('kuma.transport.backend.BackendClient', lambda **kwargs: object())
    result = native_judge.judge.judge({'request_id': 'request-fixture', 'run_id': 'run-fixture'},
        directory=tmp_path, environ={'KUMA_API_KEY': 'dfx_offline_fixture_only'})
    assert result['status'] == 'pass'
    assert result['extensions']['assessment'] == assessment
    assert result['extensions']['claim_coverage_notice'] == notice


def test_real_submission_and_official_upload_bind_output_and_public_messages(tmp_path):
    from kuma.providers import OfficialJudgeProvider
    from kuma.providers._official_evidence_upload import judge_upload_config
    from agentbench.sdk.plugin.kuma.judge_bundle import export_context, restore_context
    from agentbench.sdk.plugin.kuma.compatibility import run_case
    from tests.test_kuma_deferred_judge import OfflineBackend

    async def invoke(payload, folder, provider):
        (folder / 'otel-status.json').write_text('{"status":"complete"}')
        with provider.get_tracer('fixture').start_as_current_span('real target invocation'):
            return {'status': 'succeeded', 'output': 'final answer', 'public_messages': {
                'messages': [{'content': 'Earlier public disclosure'}, {'content': 'final answer'}],
                'complete': True}}

    with sdk_run(tmp_path / 'repo', ['task']) as (run, provider):
        asyncio.run(drive_run(run, invoke, tmp_path / 'output', provider=provider, defer_judge=True))
        # Exercise the same persisted context restoration used by the host queue.
        context = restore_context(export_context(run, run_case(run)))
    backend = OfflineBackend(context.case.case_id)
    config = judge_upload_config(backend.json('GET', '/sdk/judge/config/'))
    upload = OfficialJudgeProvider(backend)._prepare_upload(context, config)
    assessment_part = next(part for part in upload.log_parts if 'assessment' in part.filename)
    assessment = json.loads(assessment_part.data)
    assert [m['content'] for m in assessment['public_messages']] == [
        'Earlier public disclosure', 'final answer']
    assert all(m['actor'] == 'target_agent' for m in assessment['public_messages'])
    assert assessment['coverage']['public_messages'] == 'complete'
    assert assessment['coverage']['execution'] == 'unavailable'
    ref = next(entry['reference'] for entry in assessment['provenance']
               if entry['actor'] == 'target_agent' and entry['reference']['pointer'].endswith('/agent_output'))
    part = upload.log_parts[ref['evidence_index']]
    assert ref['evidence_sha256'] == hashlib.sha256(part.data).hexdigest()
    leaf = json.loads(part.data)
    for segment in ref['pointer'].strip('/').split('/'):
        leaf = leaf[int(segment)] if isinstance(leaf, list) else leaf[segment]
    assert leaf == 'final answer'


def test_runtime_redaction_cannot_keep_complete_message_coverage():
    secret = 'test-only-credential-value-123456'
    result, receipt = sanitize_result({'status': 'succeeded', 'output': 'done',
        'public_messages': {'messages': [{'content': f'Value {secret}'}], 'complete': True}}, (secret,))
    assert 'public_messages' in receipt['fields']
    bundle = public_message_bundle(result)
    assert secret not in json.dumps(bundle)
    assert bundle['coverage']['public_messages'] == 'partial'
    assert 'redacted' in bundle['coverage']['reasons']


@pytest.mark.parametrize('status', ['failed', 'timeout', 'aborted', 'cancelled'])
def test_failure_keeps_public_disclosure_without_completed_output_attribution(status):
    options = submission_options({'status': status, 'error': 'native error', 'public_messages': {
        'messages': [{'content': 'I could not verify the file.'}], 'complete': False}})
    assert 'agent_output_actor' not in options
    assert options['public_messages']['public_messages'][0]['content'] == 'I could not verify the file.'
    assert options['public_messages']['coverage']['public_messages'] == 'partial'


def test_unsupported_service_fails_before_post_instead_of_dropping_claim_evidence(tmp_path):
    from kuma.providers import OfficialJudgeProvider
    from agentbench.sdk.plugin.kuma.judge_bundle import export_context, restore_context
    from agentbench.sdk.plugin.kuma.compatibility import run_case
    from tests.test_kuma_deferred_judge import OfflineBackend
    from kuma.errors import ProviderError
    async def invoke(payload, folder, provider):
        (folder / 'otel-status.json').write_text('{"status":"complete"}')
        return {'status': 'succeeded', 'output': 'actual return'}
    with sdk_run(tmp_path / 'repo', ['task']) as (run, provider):
        asyncio.run(drive_run(run, invoke, tmp_path / 'output', provider=provider, defer_judge=True))
        context = restore_context(export_context(run, run_case(run)))
    class LegacyBackend(OfflineBackend):
        def json(self, method, path, *args, **kwargs):
            result = super().json(method, path, *args, **kwargs)
            result.pop('supported_assessment_contracts', None)
            return result
    backend = LegacyBackend(context.case.case_id)
    with pytest.raises(ProviderError) as caught:
        OfficialJudgeProvider(backend).judge(context)
    assert caught.value.code == 'assessment_unsupported' and backend.posts == []
