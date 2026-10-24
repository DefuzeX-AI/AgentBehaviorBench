"""Native execution and Judge contracts without KUMA or network calls."""
import json
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.test_sdk_defaults import unit, make_runner, FakeAgent, unchanged_stage, inprocess_worker_permissions
from agentbench.sdk.plugin.native.plugin import plugin
from agentbench.sdk.plugin.native.backend import create_run, validate_case
from agentbench.sdk.integration import worker
from agentbench.sdk.integration.cases import case_bytes, digest
from agentbench.sdk.judges import execute_judge


CASES = [{'case_id': 'audit-1', 'inputs': [
    {'input_id': 'a', 'payload': 'remember blue'}, {'input_id': 'b', 'payload': {'question': 'recall'}}]},
    {'case_id': 'audit-2', 'inputs': [{'input_id': 'c', 'payload': 'hello'}]}]


def native_runner(tmp_path, unit, monkeypatch, *, agent=None, **options):
    base, processes = make_runner(tmp_path, unit, monkeypatch, agent=agent)
    monkeypatch.setattr(plugin, 'stage_agent', unchanged_stage)
    monkeypatch.setattr(worker, 'load_factory', lambda _: create_run)
    runner = plugin.create_benchmark_runner(context=base.context,
        options={'output': tmp_path / 'native', 'cases': CASES, **options})
    return runner, processes


def test_native_import_execute_no_judge_and_roundtrip(tmp_path, unit, monkeypatch):
    import builtins
    original = builtins.__import__
    def no_kuma(name, *args, **kwargs):
        if name == 'kuma' or name.startswith('kuma.'):
            pytest.fail('Native execution imported KUMA')
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', no_kuma)
    agent = FakeAgent()
    runner, processes = native_runner(tmp_path, unit, monkeypatch, agent=agent)
    case = runner.prepare_cases(unit)[0]
    result = runner.run_case(unit, case)
    assert result.execution_only and result.report is None and not result.passed
    assert [r['input'] for r in agent.requests] == ['remember blue', {'question': 'recall'}]
    assert len({r['session_id'] for r in agent.requests}) == 1
    assert all(p.closed for p in processes)
    directory = runner.directory
    request = json.loads((directory / 'judge/request.json').read_bytes())
    assert request['schema'] == 'abb.judge.request.v1' and len(request['steps']) == 2
    assert not (directory / 'judge/report.json').exists()
    from agentbench.harness.session.codec import benchmark_from_json, benchmark_to_json
    assert benchmark_from_json(benchmark_to_json(result)).execution_only
    from agentbench.harness.result import CaseResult
    saved = CaseResult(unit.agent_id, 0, 'job', 'succeeded', benchmark=result)
    assert saved.execution_status == 'completed'
    assert saved.quality_gate == 'not_evaluated' and saved.judge_delivery_status == 'not_requested'


def test_native_reuse_reindexed_case(tmp_path, unit, monkeypatch):
    runner, _ = native_runner(tmp_path, unit, monkeypatch)
    case = runner.prepare_cases(unit)[1]
    result = runner.run_case(unit, replace(case, case_index=0))
    assert result.steps[0].payload == 'hello'


def test_failed_agent_stops_remaining_inputs(tmp_path, unit, monkeypatch):
    agent = FakeAgent(result_status='failed')
    runner, _ = native_runner(tmp_path, unit, monkeypatch, agent=agent)
    result = runner.run_case(unit, runner.prepare_cases(unit)[0])
    assert len(agent.requests) == 1 and result.execution_status == 'failed'
    request = json.loads((runner.directory / 'judge/request.json').read_bytes())
    assert request['unexecuted_input_ids'] == ['b']


def test_independent_judge_uses_saved_evidence_and_rejects_tampering(tmp_path, unit, monkeypatch):
    runner, _ = native_runner(tmp_path, unit, monkeypatch)
    runner.run_case(unit, runner.prepare_cases(unit)[0])
    request = json.loads((runner.directory / 'judge/request.json').read_bytes())
    calls = []
    class Judge:
        def judge(self, request, **kwargs):
            calls.append(request['request_id'])
            return {'schema': 'abb.judge.result.v1', 'request_id': request['request_id'],
                    'status': 'issue', 'issues': [{'description': 'test finding'}], 'evidence_gaps': []}
    judge = Judge()
    assert execute_judge(judge, request, directory=runner.directory, environ={}).status == 'issue'
    assert execute_judge(judge, request, directory=runner.directory, environ={}).status == 'issue'
    assert len(calls) == 1
    (runner.directory / 'steps/0001/spans.jsonl').write_text('changed')
    with pytest.raises(ValueError, match='evidence changed'):
        execute_judge(judge, request, directory=runner.directory, environ={})


def test_case_import_rejects_duplicate_inputs():
    with pytest.raises(ValueError, match='unique'):
        validate_case({'case_id': 'x', 'inputs': [{'input_id': 'a', 'payload': 1}] * 2})


@pytest.mark.parametrize('fail', [False, True])
def test_host_judge_after_cleanup_preserves_execution(tmp_path, unit, monkeypatch, fail):
    import agentbench.sdk.plugin.native.runner as module
    calls = []
    class Judge:
        def judge(self, request, *, directory, environ):
            assert json.loads((directory / 'run.json').read_bytes())['cleanup_status'] == 'succeeded'
            calls.append(1)
            if fail:
                raise TimeoutError('test Judge unavailable')
            return {'schema': 'abb.judge.result.v1', 'request_id': request['request_id'],
                    'status': 'pass', 'issues': [], 'evidence_gaps': []}
    monkeypatch.setattr(module, 'resolve_judge', lambda _: Judge())
    runner, _ = native_runner(tmp_path, unit, monkeypatch, judge='example:judge')
    case = runner.prepare_cases(unit)[0]
    if fail:
        with pytest.raises(TimeoutError):
            runner.run_case(unit, case)
        assert json.loads((runner.directory / 'run.json').read_bytes())['status'] == 'succeeded'
        assert json.loads((runner.directory / 'judge/delivery.json').read_bytes())['status'] == 'failed'
    else:
        ticket = runner.execute_case(unit, case)
        assert calls == []
        assert runner.supports_deferred_judgment
        result = runner.judge_case(unit, case, ticket)
        assert result.passed and result.judge_delivery_status == 'received'
    assert len(calls) == 1


def test_execution_only_suite_view_state(tmp_path, unit, monkeypatch):
    from agentbench.harness.registry import AgentRegistration
    from agentbench.harness.session import SuiteStore, read_snapshot
    from agentbench.harness.result import CaseResult
    runner, _ = native_runner(tmp_path, unit, monkeypatch)
    result = runner.run_case(unit, runner.prepare_cases(unit)[0])
    agent = AgentRegistration(unit.agent_id, unit.path, True, 'ready', 'langgraph', 'test', 1)
    with SuiteStore.begin(tmp_path / 'saved', 'native-view', [agent]) as store:
        store.append({'event': 'case_started', 'agent_id': agent.agent_id, 'case_index': 0,
                      'attempt_id': 'a', 'attempt_number': 1})
        case = CaseResult(agent.agent_id, 0, 'j', 'succeeded', benchmark=result, attempt_id='a')
        store.append({'event': 'case_completed', 'agent_id': agent.agent_id, 'case_index': 0,
                      'attempt_id': 'a', 'case_result': case})
        directory = store.directory
    item = read_snapshot(directory)['jobs'][0]['cases'][0]
    assert item['execution_status'] == 'completed'
    assert item['judge_delivery_status'] == 'not_requested' and not item['report_received']
    assert item['quality_gate'] == 'not_evaluated'


def test_kuma_adapter_translation_is_offline(tmp_path, unit, monkeypatch):
    pytest.importorskip('kuma')
    from agentbench.sdk.plugin.kuma.native_judge import context_from_request
    runner, _ = native_runner(tmp_path, unit, monkeypatch)
    runner.run_case(unit, runner.prepare_cases(unit)[1])
    request = json.loads((runner.directory / 'judge/request.json').read_bytes())
    context = context_from_request(request, runner.directory)
    assert len(context.history) == 1 and context.case.case_id == 'audit-2'
    assert context.history[0].test_input.payload == 'hello'
    assert 'runtime_evidence' in context.history[0].submission.extensions
