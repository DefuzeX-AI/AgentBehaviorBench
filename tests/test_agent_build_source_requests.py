"""Existing source questions are fulfilled internally, with privacy and byte limits."""
import copy
from dataclasses import replace
from types import SimpleNamespace

from agentbench.onboarding.build_agent_env.openrouter_provider.context import collect_context
from agentbench.onboarding.build_agent_env.openrouter_provider.settings import load_settings
from agentbench.onboarding.build_agent_env.openrouter_provider.source_requests import add_source_files
from tests.agent_build_fixtures import source, plan, Client, build


class SourceClient(Client):
    def generate(self, payload, **kwargs):
        response = super().generate(payload, **kwargs)
        if 'target_path' not in payload and not any(item['path'] == 'src/pkg/contract.py'
                for item in payload['context']['files']):
            return {**response, 'status': 'needs_input', 'bindings': [],
                    'missing_information': ['Provide src/pkg/contract.py to verify the public input.']}
        return response


def test_existing_source_request_is_fulfilled_and_restored_on_resume(source, plan):
    secret = 'source-private-token-987654'
    source_code = f'# 中文 source\nTOKEN="{secret}"\nraise AssertionError("never execute source")\n'
    (source.directory / 'agent/src/pkg/contract.py').write_text(source_code, encoding='utf-8')
    client = SourceClient(plan)
    assert build(source, plan, client=client, environ={'TOKEN': secret}).status == 'generated'
    planning = [p for p in client.requests if 'target_path' not in p]
    assert len(planning) == 2 and 'source_request_response' in planning[1]
    context = next(item for item in planning[1]['context']['files'] if item['path'] == 'src/pkg/contract.py')
    assert '中文' in context['content'] and secret not in context['content']
    resumed = SourceClient(plan)
    assert build(source, plan, client=resumed, environ={'TOKEN': secret}).status == 'generated'
    assert resumed.requests == resumed.reviews == []


def test_secret_paths_and_missing_files_do_not_trigger_followup(source, plan):
    private = source.directory / 'agent/.env'
    private.write_text('TOKEN=PRIVATE_VALUE', encoding='utf-8')
    def question(payload):
        if 'target_path' not in payload:
            return {**plan, 'status': 'needs_input', 'bindings': [],
                    'missing_information': ['Provide .env and ../outside.py and missing.py']}
    client = Client(plan, callback=question)
    assert build(source, plan, client=client).status == 'needs_input'
    assert len(client.requests) == 1
    assert not any('PRIVATE_VALUE' in repr(p) for p in client.requests)


def test_requested_source_has_separate_explicit_byte_and_file_bounds(source, tmp_path):
    (source.directory / 'agent/src/pkg/contract.py').write_text('界' * 100, encoding='utf-8')
    settings = replace(load_settings(), max_requested_file_bytes=11, max_requested_context_bytes=20, max_files=1)
    session = SimpleNamespace(source=source, settings=settings, environ={}, attempt=tmp_path,
                              context={'files': [], 'omitted': [], 'content_bytes': 0})
    assert add_source_files(session, ['src/pkg/contract.py', 'README.md']) == ['src/pkg/contract.py']
    item = session.context['files'][0]
    assert item['content'] == '界' * 3 and item['truncated']
    assert session.context['content_bytes'] == 9


def test_truncated_source_is_expanded_and_unchanged_content_stops_followups(source, tmp_path):
    path = source.directory / 'agent/src/pkg/state.py'
    path.write_text('VALUE="' + '中文' * 50 + '"\n', encoding='utf-8')
    settings = replace(load_settings(), max_file_bytes=24)
    session = SimpleNamespace(source=source, settings=settings, environ={}, attempt=tmp_path,
                              context=collect_context(source, settings, {}))
    assert next(p for p in session.context['files'] if p['path'] == 'src/pkg/state.py')['truncated']
    assert add_source_files(session, ['src/pkg/state.py']) == ['src/pkg/state.py']
    assert not next(p for p in session.context['files'] if p['path'] == 'src/pkg/state.py')['truncated']
    assert add_source_files(session, ['src/pkg/state.py']) == []
