import builtins
import json
import pytest
from agentbench.sdk.plugin.local.provider import verdict
from agentbench.sdk.plugin.local.plugin import plugin
from agentbench.sdk.plugin.local import provider
from tests.test_native_cases import native_runner, CASES
from tests.test_sdk_defaults import unit, unchanged_stage, inprocess_worker_permissions


def test_local_complete_workflow_blocks_kuma(tmp_path, unit, monkeypatch):
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name == 'kuma' or name.startswith('kuma.'):
            pytest.fail('Independent local workflow imported KUMA')
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guarded)
    base, _ = native_runner(tmp_path, unit, monkeypatch)
    (unit.path/'requirement.md').write_text('---\ninput_type: text\n---\nEcho text.')
    from agentbench.sdk.plugin.local import generation
    monkeypatch.setattr(generation, 'judge_model', lambda _: type('M', (), {'model':'test', 'base_url':'http://localhost'})())
    def generate(model, steps, *, normalize, payload, **kwargs):
        assert payload['agent_context']['environment_scope'] == 'sdk_controller'
        assert 'process' in payload['agent_context']['execution_environment']
        return normalize({'inputs':[{'input_id':'a','payload':str(payload['case_index'])}]}, set()), '{}'
    monkeypatch.setattr(generation, 'ask_model', generate)
    monkeypatch.setattr(plugin, 'stage_agent', unchanged_stage)
    monkeypatch.setattr('agentbench.sdk.plugin.local.native_runner.judge_model', lambda _: None)
    monkeypatch.setattr(provider, 'judge_model', lambda _: type('M', (), {'model':'test', 'base_url':'http://localhost'})())
    seen = []
    def ask(model, steps, **kwargs):
        seen.append(steps)
        return {'status':'pass', 'confidence':'high', 'issues':[], 'evidence_gaps':[]}, '{}'
    monkeypatch.setattr(provider, 'ask_model', ask)
    runner = plugin.create_benchmark_runner(context=base.context, options={'output':tmp_path/'local'})
    cases = runner.prepare_cases(unit)
    result = runner.run_case(unit, cases[0])
    assert result.passed and result.judge_delivery_status == 'received'
    assert seen and 'spans.jsonl' in seen[0][0]['traces']
    assert len(cases) == unit.case_count


def test_local_does_not_label_execution_failure_a_defect(tmp_path, unit, monkeypatch):
    from tests.test_sdk_defaults import FakeAgent
    from agentbench.sdk.judges import execute_judge
    runner, _ = native_runner(tmp_path, unit, monkeypatch, agent=FakeAgent(result_status='failed'))
    runner.run_case(unit, runner.prepare_cases(unit)[0])
    request = json.loads((runner.directory/'judge/request.json').read_bytes())
    monkeypatch.setattr(provider, 'ask_model', lambda *a, **kw: pytest.fail('Should not call model'))
    report = execute_judge(provider.judge, request, directory=runner.directory, environ={})
    assert report.status == 'inconclusive' and not report.issues


def test_local_rejects_uncited_or_inconsistent_findings():
    with pytest.raises(ValueError):
        verdict({'status':'issue','confidence':'high','issues':[], 'evidence_gaps':[]}, {'a'})
    with pytest.raises(ValueError):
        verdict({'status':'issue','confidence':'high','issues':[{'input_id':'unknown','message':'bad'}], 'evidence_gaps':[]}, {'a'})



def test_generated_case_rejects_invalid_schema_and_steps(tmp_path, unit, monkeypatch):
    from agentbench.sdk.plugin.local import generation
    (unit.path/'requirement.md').write_text('---\ninput_type: structured\ninput_schema: input.json\n---\nAccept x.')
    (unit.path/'input.json').write_text('{"type":"object","required":["x"],"properties":{"x":{"type":"integer"}}}')
    monkeypatch.setattr(generation, 'judge_model', lambda _: type('M', (), {'model':'test','base_url':'http://localhost'})())
    def bad(model, steps, *, normalize, **kwargs):
        return normalize({'inputs':[{'input_id':'a','payload':{'x':'wrong'}}]}, set()), '{}'
    monkeypatch.setattr(generation, 'ask_model', bad)
    import jsonschema
    with pytest.raises(jsonschema.ValidationError):
        generation.generate_cases(unit, limit=1, environ={}, output=tmp_path)
    def too_many(model, steps, *, normalize, **kwargs):
        return normalize({'inputs':[{'input_id':i,'payload':{'x':1}} for i in ('a','b')]}, set()), '{}'
    monkeypatch.setattr(generation, 'ask_model', too_many)
    with pytest.raises(ValueError, match='step budget'):
        generation.generate_cases(unit, limit=1, environ={}, output=tmp_path)


def test_profile_references_cannot_escape_or_fetch_network(tmp_path, unit):
    from agentbench.sdk.plugin.local.generation import agent_context
    (unit.path/'requirement.md').write_text('---\ninput_type: structured\ninput_schema: ../outside.json\n---\nAgent')
    with pytest.raises(ValueError, match='escapes'):
        agent_context(unit)
    (unit.path/'requirement.md').write_text('---\ninput_type: structured\ninput_schema: input.json\n---\nAgent')
    (unit.path/'input.json').write_text('{"$ref":"https://example.com/schema"}')
    with pytest.raises(ValueError, match='internal'):
        agent_context(unit)


def test_raw_response_is_retained_before_invalid_verdict_validation(tmp_path, monkeypatch):
    import io
    from agentbench.sdk.plugin.local import relay
    from agentbench.sdk.common.artifacts import Artifacts
    response = {'choices':[{'finish_reason':'stop', 'message':{'content':'{"status":"pass","confidence":"high"}'}}], 'debug':'test-secret'}
    monkeypatch.setattr(relay.urllib.request, 'urlopen', lambda *a, **kw: io.BytesIO(json.dumps(response).encode()))
    files = Artifacts(tmp_path, environ={'OPENROUTER_API_KEY':'test-secret'})
    with pytest.raises(ValueError, match='issues and evidence_gaps'):
        relay.ask_model(relay.JudgeModel('https://example.test/v1','test','test-secret'),
            [{'input_id':'a'}], normalize=verdict,
            on_response=lambda data: files.save('raw.json', data))
    retained = (tmp_path/'raw.json').read_text()
    assert 'test-secret' not in retained
    saved = json.loads(retained)
    assert saved['choices'] == response['choices']
