"""Timings survive fresh readers, interrupted processes and concurrent Cases."""
from concurrent.futures import ThreadPoolExecutor
import subprocess
import sys
import threading

import pytest

from agentbench.observe.timing import span, timing_session
from agentbench.observe.view_api import RunViewAPI
from agentbench.observe.timeline import timeline


def test_reopen_completed_journal_preserves_nested_monotonic_durations(tmp_path, monkeypatch):
    import agentbench.observe.timing as timing
    mono, wall = [0], [1_000_000_000_000]
    monkeypatch.setattr(timing.time, 'perf_counter_ns', lambda: mono[0])
    monkeypatch.setattr(timing.time, 'time_ns', lambda: wall[0])
    with timing_session(tmp_path / 'timing.jsonl', source='host', name='Evaluation'):
        mono[0] += 2_000_000
        with span('Build image', kind='build'):
            wall[0] -= 5_000_000_000  # Wall clock correction cannot make duration negative.
            mono[0] += 30_000_000
        mono[0] += 8_000_000
    first = timeline(RunViewAPI(tmp_path))['operations']
    second = timeline(RunViewAPI(tmp_path))['operations']
    assert first == second
    root, child = first
    assert root['duration_ms'] == 40
    assert child['duration_ms'] == 30
    assert child['parent_id'] == root['id']
    assert root['status'] == child['status'] == 'succeeded'


def test_failed_stage_and_cleanup_are_retained_without_exception_text(tmp_path):
    with pytest.raises(ValueError, match='private-value'):
        with timing_session(tmp_path / 'timing.jsonl', source='host', name='Evaluation'):
            try:
                with span('Submit', kind='sdk_wait'):
                    raise ValueError('private-value')
            finally:
                with span('Cleanup', kind='cleanup'):
                    pass
    records = timeline(RunViewAPI(tmp_path))['operations']
    assert [s['status'] for s in records] == ['failed', 'failed', 'succeeded']
    assert 'private-value' not in (tmp_path / 'timing.jsonl').read_text()


def test_concurrent_case_recorders_do_not_share_parents_or_files(tmp_path):
    barrier = threading.Barrier(2)
    def run(index):
        directory = tmp_path / str(index)
        directory.mkdir()
        with timing_session(directory / 'timing.jsonl', source='host', name=f'Case {index}'):
            barrier.wait(timeout=3)
            with span('Work'):
                pass
        return timeline(RunViewAPI(directory))['operations']
    with ThreadPoolExecutor(2) as pool:
        left, right = list(pool.map(run, [0, 1]))
    assert left[1]['parent_id'] == left[0]['id']
    assert right[1]['parent_id'] == right[0]['id']
    assert left[0]['clock_id'] != right[0]['clock_id']


def test_killed_process_retains_start_record_and_partial_tail_is_readable(tmp_path):
    script = '''import os, sys
from pathlib import Path
from agentbench.observe.timing import timing_session, span
with timing_session(Path(sys.argv[1]) / 'timing.jsonl', source='worker', name='Worker'):
    with span('Interrupted call'):
        os._exit(17)
'''
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path)], check=False)
    assert result.returncode == 17
    with (tmp_path / 'timing.jsonl').open('a') as stream:
        stream.write('{"incomplete":')
    view = timeline(RunViewAPI(tmp_path))
    assert len(view['operations']) == 2
    assert all(s['status'] == 'running' for s in view['operations'])
    assert view['warnings']


def test_timeline_endpoint_and_worker_file_survive_reader_restart(tmp_path):
    (tmp_path / 'evaluation').mkdir()
    with timing_session(tmp_path / 'timing.jsonl', source='host', name='Evaluation'):
        pass
    with timing_session(tmp_path / 'evaluation/timing.jsonl', source='worker', name='SDK worker'):
        with span('Agent turn', kind='agent', input_id='one'):
            pass
    path = f'/api/observe/runs/{tmp_path.name}/timeline'
    first = RunViewAPI(tmp_path).route(path, {})
    second = RunViewAPI(tmp_path).route(path, {})
    assert first['operations'] == second['operations']
    assert len(first['operations']) == 3


def test_timing_reader_never_follows_outside_symlink(tmp_path):
    outside = tmp_path / 'outside'
    outside.mkdir()
    with timing_session(outside / 'timing.jsonl', source='host', name='Secret run'):
        pass
    selected = tmp_path / 'selected'
    selected.mkdir()
    try:
        (selected / 'timing.jsonl').symlink_to(outside / 'timing.jsonl')
    except OSError:
        pytest.skip('symlink privilege unavailable')
    result = timeline(RunViewAPI(selected))
    assert result['operations'] == [] and result['warnings']


def test_suite_replay_keeps_queue_retry_and_shared_preparation_times():
    from agentbench.harness.session.snapshot import suite_snapshot
    plan = {'suite_id': 'test', 'agents': [{'agent_id': 'agent', 'case_count': 1}]}
    base = {'agent_id': 'agent', 'case_index': 0}
    events = [
        {'event': 'progress', 'agent_id': 'agent', 'phase': 'generate', 'artifact_run_id': 'generation'},
        {**base, 'event': 'case_prepared', 'timestamp': '2026-01-01T00:00:00Z'},
        {**base, 'event': 'attempt_dispatched', 'attempt_id': 'first', 'timestamp': '2026-01-01T00:00:02Z'},
        {**base, 'event': 'retry_scheduled', 'timestamp': '2026-01-01T00:00:04Z'},
        {**base, 'event': 'retry_released', 'timestamp': '2026-01-01T00:00:09Z'},
        {**base, 'event': 'attempt_dispatched', 'attempt_id': 'second', 'timestamp': '2026-01-01T00:00:10Z'},
    ]
    case = suite_snapshot(plan, events)['jobs'][0]['cases'][0]
    assert case['preparation_runs'] == ['generation']
    first, second = case['attempts']
    assert first['queued_at'] == '2026-01-01T00:00:00Z'
    assert second['queued_at'] == second['retry_released_at'] == '2026-01-01T00:00:09Z'
    assert second['retry_wait_started_at'] == '2026-01-01T00:00:04Z'
