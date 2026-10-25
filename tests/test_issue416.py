"""Issue 416: ACP permission requests and ABB's automatic answer reach the Judge.

The KUMA trace contract keeps span names and tool arguments/results, but drops
span event attributes. A bare ``acp.permission`` event therefore hid both the
requested action and the harness decision from the Judge.
"""
import asyncio
import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from agentbench.observe.acp_evidence.permissions import (MAX_ITEMS, MAX_RAW_INPUT_BYTES, MAX_TEXT,
                                                         SPAN_NAME, permission_evidence)
from agentbench.observe.invocation import InvocationObservation
from tests.sdk_fixtures.issue_run import profile

SECRET = 'sk-issue416-' + 'x' * 24
OPTIONS = [{'optionId': 'allow_once', 'name': 'Allow once', 'kind': 'allow_once'},
           {'optionId': 'reject_once', 'name': 'Reject', 'kind': 'reject_once'}]


@contextmanager
def sdk_run(repo, inputs):
    """Offline KUMA Run whose provider uses public resource metadata only, as the worker does.

    A bare TracerProvider adds resource fields the KUMA allowlist drops, which
    would mark every capture partial regardless of the spans under test.
    """
    from kuma import create_run
    from kuma.otel import configure_trace_evidence
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    provider = TracerProvider(resource=Resource({'service.name': 'abb-evaluation'}))
    capture = configure_trace_evidence(provider)
    run = create_run(repo_path=repo, agent_profile_path=profile(repo),
        case_provider=lambda ctx: {'case_id': 'offline-case', 'input_type': 'text', 'inputs': [
            {'input_id': f'input-{i}', 'payload_type': 'text', 'payload': text} for i, text in enumerate(inputs)]},
        judge_provider=lambda ctx: {'status': 'pass', 'summary': 'Offline contract test', 'issues': []},
        allow_local=True, track_files=False, trace_evidence=capture, max_steps=len(inputs))
    try:
        yield run, provider
    finally:
        if run.state in ('ready', 'input_delivered'):
            run.cancel()
        provider.shutdown()


def permission(**tool_call):
    return {'session_id': 'session-1', 'tool_call': {'toolCallId': 'call-1', **tool_call},
            'options': OPTIONS, 'outcome': {'outcome': 'selected', 'optionId': 'allow_once'},
            'decided_by': 'abb_permission_policy', 'policy': 'allow_once'}


def test_projection_keeps_action_and_decision_bounded_and_redacted():
    request, decision = permission_evidence(permission(
        title='rm config.json', kind='execute', status='pending',
        rawInput={'command': 'rm config.json', 'env': {'OPENAI_API_KEY': SECRET}, 'note': SECRET},
        content=[{'type': 'diff', 'path': 'config.json', 'oldText': 'x' * 100_000, 'newText': ''}],
        locations=[{'path': f'/workspace/{index}.txt'} for index in range(MAX_ITEMS + 3)]), [SECRET])
    call = request['tool_call']
    assert request['method'] == 'session/request_permission' and request['requested_by'] == 'target_agent'
    assert (call['toolCallId'], call['title'], call['kind']) == ('call-1', 'rm config.json', 'execute')
    assert request['options'] == OPTIONS
    assert call['rawInput']['command'] == 'rm config.json'
    assert SECRET not in json.dumps([request, decision])
    # Diff bodies are counted, not copied; locations are bounded.
    assert call['content_items'] == 1 and 'content' not in call
    assert len(call['locations']) == MAX_ITEMS and call['locations_omitted'] == 3
    assert decision['decided_by'] == 'abb_permission_policy' and decision['automatic'] is True
    assert decision['policy'] == 'allow_once' and decision['outcome'] == 'selected'
    assert decision['selected_option_id'] == 'allow_once'
    assert decision['selected_option_kind'] == 'allow_once'
    assert 'no user' in decision['note']


def test_projection_omits_oversized_input_and_truncates_text():
    request, _ = permission_evidence({**permission(title='t' * (MAX_TEXT * 4), rawInput={'blob': 'y' * MAX_RAW_INPUT_BYTES}),
                                      'options': OPTIONS * MAX_ITEMS})
    call = request['tool_call']
    assert call['rawInput_omitted'] == 'size_limit' and 'rawInput' not in call
    assert len(call['title']) == MAX_TEXT + 1
    assert len(request['options']) == MAX_ITEMS and request['options_omitted'] == len(OPTIONS) * MAX_ITEMS - MAX_ITEMS
    assert len(json.dumps(request)) < 16 * 1024


def test_denied_request_records_cancelled_harness_decision():
    _, decision = permission_evidence({**permission(title='Write file'), 'policy': 'deny',
                                       'outcome': {'outcome': 'cancelled'}})
    assert decision['outcome'] == 'cancelled' and decision['policy'] == 'deny'
    assert 'selected_option_id' not in decision and decision['automatic'] is True


def test_sdk_trace_evidence_carries_request_and_automatic_answer(tmp_path, monkeypatch):
    monkeypatch.setenv('ISSUE416_API_KEY', SECRET)
    with sdk_run(tmp_path / 'repo', ['Delete config.json']) as (run, provider):
        run.get_input()
        folder = tmp_path / 'observation'
        observed = InvocationObservation(folder, 'invoke', run.run_id, 'acp', provider=provider)
        observed.store.record('execution_start', input='Delete config.json')
        callback = observed.callbacks[0]
        callback.on_acp_event('session_update', {'update': {
            'sessionUpdate': 'tool_call', 'toolCallId': 'call-1', 'title': 'rm config.json',
            'kind': 'execute', 'status': 'pending', 'rawInput': {'command': 'rm config.json'}}})
        callback.on_acp_event('permission', permission(
            title='rm config.json', kind='execute', rawInput={'command': 'rm config.json', 'token': SECRET}))
        callback.on_acp_event('session_update', {'update': {
            'sessionUpdate': 'tool_call_update', 'toolCallId': 'call-1', 'status': 'completed',
            'rawOutput': {'exit_code': 0}}})
        callback.on_acp_event('prompt_completed', {'stopReason': 'end_turn'})
        observed.store.record('execution_end', output='Deleted')
        observed.close()
        run.submit(output='Deleted', status='completed')

        evidence = run.history[0].submission.extensions['trace_evidence']
        component = run.history[0].submission.capture_status.traces
    assert SECRET not in json.dumps(evidence, default=dict)
    # Only allowlisted semantic fields are used: capture stays complete.
    assert component.status == 'complete', evidence['reasons']
    spans = {span['name']: span for span in evidence['spans']}
    asked, tool = spans[SPAN_NAME], spans['rm config.json']
    assert asked['parent_span_id'] == tool['span_id']
    assert dict(asked['tool_content_status']) == {'arguments': 'present', 'result': 'present'}
    attributes = asked['attributes']
    request = attributes['gen_ai.tool.call.arguments']
    decision = attributes['gen_ai.tool.call.result']
    assert request['tool_call']['title'] == 'rm config.json' and request['tool_call']['kind'] == 'execute'
    assert request['tool_call']['toolCallId'] == 'call-1'
    assert [option['optionId'] for option in request['options']] == ['allow_once', 'reject_once']
    assert decision['selected_option_id'] == 'allow_once'
    assert (decision['decided_by'], decision['automatic']) == ('abb_permission_policy', True)
    # The native ID stays unique to the requested tool, for tool/model linking.
    assert 'gen_ai.tool.call.id' not in attributes
    assert tool['attributes']['gen_ai.tool.call.id'] == 'call-1'
    summary = json.loads((folder / 'acp-summary.json').read_text())
    assert summary['permission_requests'] == 1 and summary['tool_calls'] == 1
    assert summary['incomplete_tools'] == []


def test_permission_without_announced_tool_uses_root_span(tmp_path):
    folder = tmp_path / 'observation'
    observed = InvocationObservation(folder, 'invoke', 'session', 'acp')
    observed.store.record('execution_start', input='write')
    observed.callbacks[0].on_acp_event('permission', permission(title='Write /tmp/x', kind='edit'))
    observed.store.record('execution_end', output='done')
    observed.close()
    spans = [json.loads(line)['data'] for line in (folder / 'otel.jsonl').read_text().splitlines()]
    root = next(span for span in spans if span['name'] == 'abb.execute')
    asked = next(span for span in spans if span['name'] == SPAN_NAME)
    assert asked['parent_span_id'] == root['span_id']
    assert json.loads(asked['attributes']['gen_ai.tool.call.result'])['outcome'] == 'selected'
    assert json.loads((folder / 'otel-status.json').read_text())['status'] == 'complete'


@pytest.mark.parametrize('policy,offered,expected', [
    ('allow_once', OPTIONS, {'outcome': 'selected', 'optionId': 'allow_once'}),
    ('deny', OPTIONS, {'outcome': 'cancelled'}),
    ('allow_once', OPTIONS[1:], {'outcome': 'cancelled'}),
])
def test_client_emits_policy_and_decider(policy, offered, expected):
    pytest.importorskip('acp')
    from acp.schema import PermissionOption, ToolCallUpdate
    from agentbench.adapter.acp.client import ACPClient
    events = []
    client = ACPClient(SimpleNamespace(permission_policy=policy), lambda name, data: events.append((name, data)))
    client.session_id = 'session-1'
    response = asyncio.run(client.request_permission(
        'session-1', ToolCallUpdate(tool_call_id='call-1', title='rm config.json', kind='execute'),
        [PermissionOption.model_validate(option) for option in offered]))
    assert response.outcome.outcome == expected['outcome']
    name, data = events[-1]
    assert name == 'permission' and data['outcome'] == expected
    assert (data['decided_by'], data['policy']) == ('abb_permission_policy', policy)
    assert data['tool_call']['title'] == 'rm config.json'
