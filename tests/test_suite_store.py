"""Persistent Suite identity, completed-result reuse and coordinator safety."""

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from agentbench.harness.registry import AgentRegistration
from agentbench.harness.result import BenchmarkResult, CaseResult
from agentbench.harness.session import SuiteStore, SuiteLockedError, SuiteProvenanceError, read_snapshot
from agentbench.sdk.contracts import PreparedCase


def registration(tmp_path, *, cases=3):
    root = tmp_path / 'agent'
    root.mkdir(exist_ok=True)
    (root / 'agent.py').write_text('def run(value): return value\n')
    return AgentRegistration('test-agent', root, True, 'ready', 'test', 'test', cases)


def prepared(tmp_path, index=0):
    path = tmp_path / f'generated-{index}.json'
    path.write_text(json.dumps({'case_id': f'case-{index}', 'inputs': ['first', 'second']}))
    return PreparedCase(index, f'case-{index}', path.resolve(), 'a' * 64,
                        hashlib.sha256(path.read_bytes()).hexdigest())


def completed(agent, index=0, *, verdict='issue', job_id='job-1'):
    report = SimpleNamespace(status=verdict, confidence=0.9, issues=('behavior',), evidence_gaps=())
    benchmark = BenchmarkResult(agent.agent_id, 'test', 'sdk-run', 'report_ready', report, (), 2)
    return CaseResult(agent.agent_id, index, job_id, 'succeeded' if verdict == 'pass' else 'failed',
                      f'case-{index}', benchmark)


def test_completed_issue_survives_restart_and_missing_slots_remain_visible(tmp_path):
    agent = registration(tmp_path)
    with SuiteStore.begin(tmp_path / 'suites', 'suite_one', [agent]) as store:
        stable = store.retain_case(agent.agent_id, prepared(tmp_path))
        store.append({'event': 'case_started', 'agent_id': agent.agent_id, 'case_index': 0,
                      'attempt_id': 'attempt-1', 'attempt_number': 1, 'job_id': 'job-1'})
        store.append({'event': 'case_completed', 'agent_id': agent.agent_id, 'case_index': 0,
                      'attempt_id': 'attempt-1', 'case_result': completed(agent)})
        store.append({'event': 'suite_failed', 'error': {'type': 'KeyboardInterrupt', 'message': 'stopped'}})
    (tmp_path / 'generated-0.json').unlink()
    with SuiteStore.open(tmp_path / 'suites', 'suite_one') as store:
        store.validate_provenance([agent], {})
        assert store.prepared_cases(agent.agent_id) == (stable,)
        restored, = store.completed_results(agent.agent_id)
        assert not restored.benchmark.passed
        assert restored.benchmark.report.status == 'issue'
        cases = store.snapshot()['jobs'][0]['cases']
        assert len(cases) == 3 and cases[0]['execution_status'] == 'completed'
        assert cases[1]['execution_status'] == 'pending_generation'
        assert store.snapshot()['counts']['judge_received'] == 1


def test_exclusive_lock_rejects_another_process_then_releases_on_close(tmp_path):
    agent = registration(tmp_path)
    store = SuiteStore.begin(tmp_path / 'suites', 'suite_lock', [agent])
    program = ('import sys\nfrom agentbench.harness.session import SuiteStore, SuiteLockedError\n'
               'try:\n s=SuiteStore.open(sys.argv[1])\n s.close()\n print("opened")\n'
               'except SuiteLockedError:\n print("locked")\n')
    try:
        observed = subprocess.check_output([sys.executable, '-c', program, str(store.directory)], text=True)
        assert observed.strip() == 'locked'
        with pytest.raises(SuiteLockedError):
            SuiteStore.open(store.directory)
    finally:
        store.close()
    observed = subprocess.check_output([sys.executable, '-c', program, str(store.directory)], text=True)
    assert observed.strip() == 'opened'


def test_source_and_model_mismatch_reject_resume_without_recording_secrets(tmp_path):
    agent = registration(tmp_path)
    secret = 'private-real-value'
    config = {'model': 'model-a', 'sdk': {'api_key': secret}, 'environ': {'FOO': secret}, 'label': secret}
    with SuiteStore.begin(tmp_path / 'suites', 'suite_config', [agent], configuration=config,
                          environ={'OPENROUTER_API_KEY': secret}) as store:
        store.append({'event': 'note', 'message': f'failed with {secret}', 'authorization': 'bearer value'})
        text = (store.directory / 'plan.json').read_text() + store.path.read_text()
        assert secret not in text and 'bearer value' not in text
        assert 'environ' not in store.plan['configuration']
        assert 'api_key' not in store.plan['configuration']['sdk']
        store.validate_provenance([agent], config)
        with pytest.raises(SuiteProvenanceError):
            store.validate_provenance([agent], {**config, 'model': 'model-b'})
        (agent.path / 'agent.py').write_text('def run(value): return "different"\n')
        with pytest.raises(SuiteProvenanceError):
            store.validate_provenance([agent], config)


def test_case_bytes_are_immutable_and_corruption_is_detected(tmp_path):
    agent = registration(tmp_path)
    with SuiteStore.begin(tmp_path / 'suites', 'suite_case', [agent]) as store:
        original = prepared(tmp_path)
        stable = store.retain_case(agent.agent_id, original)
        assert stable.artifact_path.is_relative_to(store.directory)
        revision = store.snapshot()['revision']
        assert store.retain_case(agent.agent_id, original) == stable
        assert store.snapshot()['revision'] == revision
        with pytest.raises(SuiteProvenanceError):
            store.retain_case(agent.agent_id, replace(original, case_id='different-case'))
        stable.artifact_path.write_text('{}')
        with pytest.raises(SuiteProvenanceError):
            store.prepared_cases(agent.agent_id)


def test_failed_atomic_write_does_not_advance_memory_or_destroy_saved_events(tmp_path, monkeypatch):
    from agentbench.harness.session import store as module
    agent = registration(tmp_path)
    with SuiteStore.begin(tmp_path / 'suites', 'suite_disk', [agent]) as store:
        before = store.path.read_bytes()
        def fail(*args):
            raise OSError('disk full')
        monkeypatch.setattr(module, 'atomic_json', fail)
        with pytest.raises(OSError, match='disk full'):
            store.append({'event': 'case_queued', 'agent_id': agent.agent_id, 'case_index': 0})
        assert store.path.read_bytes() == before
        assert store.snapshot()['revision'] == 1


def test_event_sequence_is_durable_and_corruption_is_rejected(tmp_path):
    agent = registration(tmp_path)
    with SuiteStore.begin(tmp_path / 'suites', 'suite_seq', [agent]) as store:
        store.append({'event': 'suite_completed', 'sequence': 999, 'summary': {}})
        directory = store.directory
    with SuiteStore.open(directory) as store:
        assert store.append({'event': 'suite_resumed', 'sequence': 1})['sequence'] == 3
    assert read_snapshot(directory)['revision'] == 3
    events = json.loads((directory / 'events.json').read_text())
    events[-1]['sequence'] = 1
    (directory / 'events.json').write_text(json.dumps(events))
    with pytest.raises(ValueError, match='sequence'):
        read_snapshot(directory)


def test_reader_does_not_require_the_live_writer_lock(tmp_path):
    with SuiteStore.begin(tmp_path / 'suites', 'suite_reader', [registration(tmp_path)]) as store:
        snapshot = read_snapshot(store.directory)
        assert snapshot['counts']['planned'] == 3
        assert snapshot['jobs'][0]['cases'][2]['case_index'] == 2


def test_plan_tampering_is_detected_before_opening_for_resume(tmp_path):
    with SuiteStore.begin(tmp_path / 'suites', 'suite_plan', [registration(tmp_path)]) as store:
        path = store.directory / 'plan.json'
    value = json.loads(path.read_text())
    value['agents'][0]['case_count'] += 1
    path.write_text(json.dumps(value))
    with pytest.raises(SuiteProvenanceError):
        SuiteStore.open(path.parent)


def test_full_report_round_trip_survives_event_bus_detachment():
    from agentbench.harness.events import _snapshot
    from agentbench.harness.session import benchmark_from_json, benchmark_to_json
    raw = {'agent_id': 'agent', 'adapter_name': 'fake', 'run_id': 'run', 'run_state': 'report_ready',
           'history_count': 1, 'provider_mode': None, 'passed': False, 'steps': [],
           'report': {'status': 'issue', 'report_id': 'report-1', 'run_id': 'run', 'case_id': 'case-1',
                      'issues': [{'code': 'memory'}], 'extensions': {'artifact_ref': ['evidence/file']}}}
    restored = benchmark_from_json(raw)
    assert restored.report.report_id == 'report-1'
    assert benchmark_to_json(_snapshot(restored)) == raw
    with pytest.raises(TypeError):
        restored.report.extensions['artifact_ref'] = 'changed'


def test_cli_agent_aggregate_preserves_recovered_report_fields(tmp_path):
    from agentbench.cli.result_export import _suite_agent_to_json
    from agentbench.harness.result import SuiteAgentResult
    from agentbench.harness.session import case_from_json, case_to_json
    agent = registration(tmp_path, cases=1)
    value = case_to_json(completed(agent))
    value['benchmark']['report'].update(report_id='original-report', extensions={
        'abb_artifact_directory': str(tmp_path / 'original-run')})
    restored = case_from_json(value)
    aggregate = _suite_agent_to_json(SuiteAgentResult(agent.agent_id, (restored,), 1))
    assert aggregate['case_results'][0]['benchmark']['report'] == value['benchmark']['report']
    assert aggregate['benchmarks'][0]['report']['report_id'] == 'original-report'


def test_sdk_wide_progress_and_non_file_case_are_supported(tmp_path):
    with SuiteStore.begin(tmp_path / 'suites', 'suite_injected', [registration(tmp_path)]) as store:
        store.append({'event': 'progress', 'agent_id': None, 'stage': 'sdk_check'})
        case = PreparedCase(0, 'memory-case')
        assert store.retain_case('test-agent', case) == case
        assert store.snapshot()['jobs'][0]['cases'][0]['resumable'] is False


def test_partial_generation_cannot_duplicate_a_case_saved_before_restart(tmp_path):
    agent = registration(tmp_path)
    with SuiteStore.begin(tmp_path / 'suites', 'suite_unique', [agent]) as store:
        original = prepared(tmp_path)
        store.retain_case(agent.agent_id, original)
        directory = store.directory
    with SuiteStore.open(directory) as store:
        with pytest.raises(ValueError, match='duplicates'):
            store.retain_case(agent.agent_id, replace(original, case_index=1))
        assert len(store.prepared_cases(agent.agent_id)) == 1
