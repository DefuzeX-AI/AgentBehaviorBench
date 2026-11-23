"""Regressions for complete Local Judge input and recorded tool-call identities."""
import io
import json
from types import SimpleNamespace

import pytest

from agentbench.sdk.plugin.local import generation, provider, relay


def _framework(root):
    path = root / 'steps/0001/framework.jsonl'
    return path, [json.loads(line) for line in path.read_text().splitlines()]


def _write_rows(path, rows):
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows))


def _fake_judge_request(root, text='x' * 140000):
    folder = root / 'steps/0001'
    folder.mkdir(parents=True)
    (folder / 'framework.jsonl').write_text(text)
    return {'request_id': 'fixture', 'evidence_status': 'complete', 'unexecuted_input_ids': [],
            'case': {'abb_agent_context': {'profile': 'fixture'}},
            'attachments': {'steps/0001/framework.jsonl': 'fixture'},
            'steps': [{'input': {'input_id': 'step-1', 'payload': 'hello'},
                       'result': {'status': 'succeeded', 'output': 'hello'},
                       'evidence_prefix': 'steps/0001'}]}


def test_full_large_evidence_reaches_judge_by_default(tmp_path, monkeypatch):
    request = _fake_judge_request(tmp_path)
    seen = []
    monkeypatch.setattr(provider, 'validate_evidence', lambda *a: None)
    monkeypatch.setattr(provider, 'judge_model', lambda e: SimpleNamespace(model='fixture', base_url='http://localhost'))
    def ask(model, steps, **kw):
        seen.append(kw['payload'])
        return {'status': 'pass', 'confidence': 'high', 'issues': [], 'evidence_gaps': []}, '{}'
    monkeypatch.setattr(provider, 'ask_model', ask)
    answer = provider.judge.judge(request, directory=tmp_path, environ={})
    assert answer['status'] == 'pass'
    assert seen[0]['steps'][0]['traces']['framework.jsonl'] == 'x' * 140000


def test_explicit_small_limit_returns_inconclusive_without_call(tmp_path, monkeypatch):
    request = _fake_judge_request(tmp_path)
    monkeypatch.setattr(provider, 'validate_evidence', lambda *a: None)
    monkeypatch.setattr(provider, 'ask_model', lambda *a, **kw: pytest.fail('Unexpected model call'))
    answer = provider.judge.judge(request, directory=tmp_path, environ={'ABB_LOCAL_JUDGE_MAX_CHARS': '1000'})
    assert answer['status'] == 'inconclusive'
    assert '1000 characters' in answer['evidence_gaps'][0]


def test_model_output_budget_and_reasoning_are_configurable(monkeypatch):
    env = {'ABB_LOCAL_JUDGE_BASE_URL': 'http://localhost/v1', 'ABB_LOCAL_JUDGE_MODEL': 'glm-5.3-flash',
           'ABB_LOCAL_JUDGE_API_KEY': 'fixture-key', 'ABB_LOCAL_JUDGE_MAX_TOKENS': '8192',
           'ABB_LOCAL_JUDGE_REASONING_EFFORT': 'low'}
    model = relay.judge_model(env)
    sent = []
    def open_url(request, timeout):
        sent.append(json.loads(request.data))
        return io.BytesIO(json.dumps({'choices': [{'finish_reason': 'stop', 'message': {'content':
            '{"status":"pass","confidence":"high","reason":"fixture","issues":[],"evidence_gaps":[]}'}}]}).encode())
    monkeypatch.setattr(relay.urllib.request, 'urlopen', open_url)
    result, _ = relay.ask_model(model, [{'input_id': 'step-1'}], normalize=provider.verdict)
    assert result['status'] == 'pass'
    assert sent[0]['max_tokens'] == 8192 and sent[0]['reasoning_effort'] == 'low'


@pytest.mark.parametrize('tokens', ['0', '-1', 'wrong'])
def test_invalid_output_budgets_rejected(tokens):
    env = {'ABB_LOCAL_JUDGE_BASE_URL': 'http://localhost/v1', 'ABB_LOCAL_JUDGE_MODEL': 'fixture',
           'ABB_LOCAL_JUDGE_API_KEY': 'fixture-key', 'ABB_LOCAL_JUDGE_MAX_TOKENS': tokens}
    with pytest.raises(ValueError, match='ABB_LOCAL_JUDGE_MAX_TOKENS'):
        relay.judge_model(env)


def test_truncated_parseable_verdict_is_rejected_but_raw_is_retained(monkeypatch):
    response = {'choices': [{'finish_reason': 'length', 'message': {'content':
        '{"status":"pass","confidence":"high","reason":"fixture","issues":[],"evidence_gaps":[]}'}}]}
    monkeypatch.setattr(relay.urllib.request, 'urlopen', lambda *a, **kw: io.BytesIO(json.dumps(response).encode()))
    retained = []
    with pytest.raises(RuntimeError, match='truncated'):
        relay.ask_model(relay.JudgeModel('http://localhost/v1', 'fixture', 'fixture-key'),
                        [{'input_id': 'step-1'}], normalize=provider.verdict, on_response=retained.append)
    assert retained == [response]


def test_judge_output_settings_do_not_leak_to_case_generation(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(generation, 'judge_model', lambda env: (seen.append(dict(env)) or
        SimpleNamespace(model='fixture', base_url='http://localhost')))
    monkeypatch.setattr(generation, 'ask_model', lambda model, steps, normalize, **kw:
        (normalize({'inputs': [{'input_id': 'step-1', 'payload': 'hello'}]}, set()), '{}'))
    env = {'ABB_LOCAL_JUDGE_MAX_TOKENS': '8192', 'ABB_LOCAL_JUDGE_REASONING_EFFORT': 'low'}
    generation.generate_cases(SimpleNamespace(case_count=1), limit=1, environ=env, output=tmp_path,
                              context={'input_type': 'text', 'references': {}})
    assert 'ABB_LOCAL_JUDGE_MAX_TOKENS' not in seen[0]
    assert 'ABB_LOCAL_JUDGE_REASONING_EFFORT' not in seen[0]
    assert env['ABB_LOCAL_JUDGE_MAX_TOKENS'] == '8192'
