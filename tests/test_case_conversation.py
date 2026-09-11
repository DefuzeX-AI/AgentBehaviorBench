import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from agentbench.sdk.common.input_binding import InputBinding
from agentbench.runtime.agentcontainer.session import AgentSession


def test_full_tool_history_is_delivered_once_and_cases_are_isolated():
    binding = InputBinding({'encoding': 'identity', 'conversation': {
        'mode': 'messages', 'input_key': 'messages', 'history_key': 'messages'}})
    conversation = binding.new_conversation()
    first = conversation.prepare('Research A')
    history = first['messages'] + [
        {'type': 'ai', 'content': '', 'tool_calls': [{'id': 't1', 'name': 'search', 'args': {'query': 'A'}}]},
        {'type': 'tool', 'content': 'source evidence', 'tool_call_id': 't1'},
        {'type': 'ai', 'content': 'Answer A'},
    ]
    conversation.commit({'status': 'succeeded', 'output': 'Answer A', 'raw_output': {'messages': history}})
    second = conversation.prepare('Compare it with B')
    assert second['messages'] == history + [{'role': 'user', 'content': 'Compare it with B'}]
    second['messages'][0]['content'] = 'caller mutation'
    assert conversation.messages[0]['content'] == 'Research A'
    assert binding.new_conversation().prepare('New case') == {
        'messages': [{'role': 'user', 'content': 'New case'}]}


def test_context_budget_fails_without_truncating_and_failed_answers_are_not_added():
    conversation = InputBinding({'encoding': 'identity', 'conversation': {
        'mode': 'messages', 'max_chars': 100}}).new_conversation()
    conversation.prepare('hello')
    conversation.commit({'status': 'failed'})
    assert conversation.messages == []
    with pytest.raises(ValueError, match='not truncated'):
        conversation.prepare('x' * 200)
    assert conversation.messages == []


def test_session_owns_one_adapter_and_refuses_other_cases(monkeypatch, tmp_path):
    from agentbench.runtime.agentcontainer import session as module
    events = []
    adapter = SimpleNamespace(load=lambda: events.append('load'), close=lambda: events.append('close'))
    monkeypatch.setattr(module.DEFAULT_ADAPTER_FACTORY, 'create', lambda _: adapter)
    session = AgentSession()
    envelope = {'agent_id': 'a', 'framework': 'langgraph', 'run_id': 'turn1', 'session_id': 'case1'}
    assert session.load(tmp_path, envelope) is adapter
    assert session.load(tmp_path, {**envelope, 'run_id': 'turn2'}) is adapter
    with pytest.raises(ValueError, match='across Cases'):
        session.load(tmp_path, {**envelope, 'session_id': 'case2'})
    asyncio.run(session.aclose())
    asyncio.run(session.aclose())
    assert events == ['load', 'close']
    assert session.snapshot()['invocations'] == 2


@pytest.mark.parametrize('explicit', [True, False])
def test_evaluate_cli_executes_ten_cases_without_clamping(starter_agent, repo_root, monkeypatch, tmp_path, explicit):
    from agentbench.cli.main import cli
    from agentbench.cli.features import evaluate
    from examples import case_file_sdk
    calls = []
    def create_run(**kwargs):
        payload = f"Independently generated task {len(calls) + 1}"
        run = case_file_sdk.Run((case_file_sdk.Input("step-1", payload),), (payload,))
        calls.append(payload)
        return run
    monkeypatch.setattr(case_file_sdk, 'create_run', create_run)
    monkeypatch.setattr(evaluate, 'enabled_agents', lambda _: [{'agent_id': starter_agent.agent_id}])
    monkeypatch.setattr(evaluate, 'resolve_agent', lambda *_: replace(starter_agent, case_count=1 if explicit else 10))
    monkeypatch.setattr(evaluate, 'load_project_environment', lambda _: None)
    monkeypatch.chdir(repo_root)
    args = ['evaluate', '1', '--sdk', 'python:examples.case_file_sdk',
            '--sdk-options', 'examples/case_file_options.json', '--result-output', str(tmp_path / 'results.json')]
    if explicit:
        args += ['--cases', '10']
    assert cli(args) == 0
    assert len(calls) == len(set(calls)) == 10


def test_max_steps_validation():
    from agentbench.sdk.kuma import benchmark
    from agentbench.harness.errors import ProviderSelectionError
    for invalid in (True, 0, -1, 1.5):
        with pytest.raises(ProviderSelectionError):
            benchmark.KumaContainerRunner(options={'max_steps': invalid})


def test_case_identity_checks_content_not_ids_and_catches_whitespace_duplicates():
    from agentbench.sdk.common.case_identity import case_content_sha256
    def case(case_id, step_id, text):
        return {'case_id': case_id, 'inputs': [{'input_id': step_id, 'payload_type': 'text', 'payload': text}]}
    first = case_content_sha256(case('one', 'step1', 'Compare A with B'))
    assert first == case_content_sha256(case('two', 'other', 'Compare A  with\nB'))
    assert first != case_content_sha256(case('one', 'step1', 'Compare C with D'))
