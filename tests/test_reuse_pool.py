"""Concurrent reuse admission preserves every execution in one live batch."""

from concurrent.futures import ThreadPoolExecutor
import multiprocessing
from pathlib import Path
import threading
import time

import pytest

from agentbench.cli.sessions import control, recovery, reuse, reuse_pool
from agentbench.harness import SuiteRunner
from agentbench.harness.session import SuiteStore, read_snapshot
from tests.test_suite_resume import RecoveryFactory, runner_for
from tests.test_suite_reuse import original_suite


class WaitingFactory(RecoveryFactory):
    def __init__(self, directory, entered, release):
        super().__init__(directory)
        self.entered, self.release = entered, release

    def open_suite(self, suite_id, signal):
        session = super().open_suite(suite_id, signal)
        create = session.create
        def bound(agent, identity, sink):
            runner = create(agent, identity, sink)
            execute = runner.run_case
            def run(agent, case, **kwargs):
                if case.case_index == 0:
                    self.entered.set()
                    while not self.release.wait(.05):
                        signal.check()
                return execute(agent, case, **kwargs)
            runner.run_case = run
            return runner
        session.create = bound
        return session


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(reuse, 'PROJECT_ROOT', tmp_path)
    monkeypatch.setattr(recovery, 'PROJECT_ROOT', tmp_path)


def until(predicate, timeout=8):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        result = predicate()
        if result:
            return result
        time.sleep(.02)
    raise AssertionError('Timed out waiting for reuse admission')


def test_same_case_and_another_agent_join_live_suite_then_next_request_starts_new_batch(tmp_path):
    source, _ = original_suite(tmp_path, agents=2)
    before = (source / 'events.json').read_bytes()
    entered, release = threading.Event(), threading.Event()
    factory = WaitingFactory(tmp_path, entered, release)
    runner = SuiteRunner(runner_factory=factory)
    destinations = []
    with ThreadPoolExecutor(3) as pool:
        first = pool.submit(reuse.execute_reuse, source, environ={}, runner=runner,
            selection={('agent-0', 1)}, command_id='one', on_created=destinations.append)
        try:
            assert entered.wait(5)
            directory = destinations[0]
            plan_before = (directory / 'plan.json').read_bytes()
            second = pool.submit(reuse.execute_reuse, source, environ={}, runner=runner_for(tmp_path)[0],
                selection={('agent-0', 1)}, command_id='two', on_created=destinations.append)
            third = pool.submit(reuse.execute_reuse, source, environ={}, runner=runner_for(tmp_path)[0],
                selection={('agent-1', 0)}, command_id='three', on_created=destinations.append)
            until(lambda: read_snapshot(directory)['counts']['planned'] == 3)
            assert len(set(destinations)) == 1
            pending = read_snapshot(directory)
            assert pending['state'] == 'running' and pending['counts']['completed'] == 0
        finally:
            release.set()
        assert first.result().result.passed and second.result().result.passed and third.result().result.passed
    snapshot = read_snapshot(directory)
    assert snapshot['counts']['completed'] == snapshot['counts']['judge_received'] == 3
    assert (directory / 'plan.json').read_bytes() == plan_before
    assert (source / 'events.json').read_bytes() == before
    assert factory.generated == [] and len(factory.executed) == 3
    cases = snapshot['jobs'][0]['cases']
    assert cases[0]['case_id'] == cases[1]['case_id'] == 'case-1'
    assert cases[0]['active_attempt_id'] != cases[1]['active_attempt_id']
    assert cases[0]['prepared_case']['artifact_path'] != cases[1]['prepared_case']['artifact_path']
    assert cases[0]['origin']['case_index'] == cases[1]['origin']['case_index'] == 1
    with SuiteStore.open(directory) as store:
        store.validate_provenance()
    next_run = reuse.execute_reuse(source, environ={}, runner=runner_for(tmp_path)[0], selection={('agent-0', 1)})
    assert next_run.directory != directory
    assert read_snapshot(next_run.directory)['counts']['planned'] == 1
    whole_batch = reuse.execute_reuse(directory, environ={}, runner=runner_for(tmp_path)[0])
    assert whole_batch.result.passed and read_snapshot(whole_batch.directory)['counts']['completed'] == 3


def test_duplicate_transport_request_while_running_adds_no_second_execution(tmp_path):
    source, _ = original_suite(tmp_path)
    entered, release = threading.Event(), threading.Event()
    factory = WaitingFactory(tmp_path, entered, release)
    destinations = []
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(reuse.execute_reuse, source, environ={}, runner=SuiteRunner(runner_factory=factory),
            selection={('agent-0', 1)}, command_id='same', on_created=destinations.append)
        try:
            assert entered.wait(5)
            second = pool.submit(reuse.execute_reuse, source, environ={}, selection={('agent-0', 1)},
                command_id='same', on_created=destinations.append)
            until(lambda: len(destinations) == 2)
            assert destinations[0] == destinations[1]
            assert read_snapshot(destinations[0])['counts']['planned'] == 1
        finally:
            release.set()
        assert first.result().directory == second.result().directory
    assert len(factory.executed) == 1
    # Re-delivery after completion requires neither credentials nor source artifacts.
    with SuiteStore.open(source) as store:
        store.prepared_case('agent-0', 1).artifact_path.unlink()
    assert reuse.execute_reuse(source, environ={}, command_id='same', selection={('agent-0', 1)}).directory == destinations[0]


@pytest.mark.parametrize('difference', ['configuration', 'source', 'credentials', 'output'])
def test_incompatible_request_creates_a_separate_suite(tmp_path, difference):
    source, agents = original_suite(tmp_path)
    entered, release = threading.Event(), threading.Event()
    destinations = []
    with ThreadPoolExecutor(1) as pool:
        first = pool.submit(reuse.execute_reuse, source, environ={},
            runner=SuiteRunner(runner_factory=WaitingFactory(tmp_path, entered, release)),
            selection={('agent-0', 1)}, on_created=destinations.append)
        try:
            assert entered.wait(5)
            args = {'environ': {}, 'runner': runner_for(tmp_path)[0], 'selection': {('agent-0', 1)}}
            if difference == 'configuration':
                # A second source with different saved semantic settings.
                sibling = tmp_path / 'second'
                sibling.mkdir()
                source2, _ = original_suite(sibling, configuration={'model': 'different'})
            else:
                source2 = source
            if difference == 'source':
                (agents[0].path / 'changed.py').write_text('new source')
            if difference == 'credentials':
                args['environ'] = {'OPENAI_API_KEY': 'different-secret-value'}
            if difference == 'output':
                args['root'] = tmp_path / 'different-output'
            second = reuse.execute_reuse(source2, **args)
            assert second.directory != destinations[0]
        finally:
            release.set()
        first.result()


def _process_reuse(root, source, command, entered, release, output):
    reuse.PROJECT_ROOT = recovery.PROJECT_ROOT = Path(root)
    factory = WaitingFactory(Path(root), entered, release)
    try:
        result = reuse.execute_reuse(source, environ={}, runner=SuiteRunner(runner_factory=factory),
            command_id=command, selection={('agent-0', 1)}, on_created=lambda path: output.put(('created', str(path))))
        output.put(('done', str(result.directory), len(factory.executed)))
    except Exception as exc:
        output.put(('error', repr(exc)))


def test_independent_processes_share_one_owner_and_two_execution_slots(tmp_path):
    source, _ = original_suite(tmp_path)
    context = multiprocessing.get_context('spawn')
    entered, release, output = context.Event(), context.Event(), context.Queue()
    processes = []
    try:
        first = context.Process(target=_process_reuse, args=(tmp_path, source, 'process-one', entered, release, output))
        first.start()
        processes.append(first)
        assert entered.wait(8)
        initial = output.get(timeout=5)
        assert initial[0] == 'created', initial
        second = context.Process(target=_process_reuse, args=(tmp_path, source, 'process-two', entered, release, output))
        second.start()
        processes.append(second)
        joined = output.get(timeout=8)
        assert joined == initial
        until(lambda: read_snapshot(initial[1])['counts']['planned'] == 2)
        release.set()
        finished = [output.get(timeout=10), output.get(timeout=10)]
        assert all(value[0] == 'done' for value in finished), finished
        assert sorted(value[2] for value in finished) == [0, 2]
        assert read_snapshot(initial[1])['counts']['completed'] == 2
    finally:
        release.set()
        for process in processes:
            process.join(10)
            if process.is_alive():
                process.terminate()
                process.join()


def test_web_controller_admits_second_click_without_waiting_for_first(tmp_path, monkeypatch):
    source, _ = original_suite(tmp_path)
    entered, release = threading.Event(), threading.Event()
    factory = WaitingFactory(tmp_path, entered, release)
    monkeypatch.setattr(reuse, 'build_saved_runner', lambda *_: SuiteRunner(runner_factory=factory))
    coordinator = control.SuiteControl(source / 'events.json', {})
    try:
        payload = {'action': 'reuse', 'agent_id': 'agent-0', 'case_index': 1}
        coordinator.submit({**payload, 'command_id': 'web-one'}, coordinator.token)
        assert entered.wait(5)
        coordinator.submit({**payload, 'command_id': 'web-two'}, coordinator.token)
        commands = until(lambda: len([c for c in coordinator.commands if c.get('result_path')]) == 2 and coordinator.commands)
        assert commands[0]['suite_id'] == commands[1]['suite_id']
        until(lambda: read_snapshot(Path(commands[0]['result_path']).parent)['counts']['planned'] == 2)
        release.set()
        until(lambda: all(c['status'] == 'completed' for c in coordinator.commands))
        assert len(factory.executed) == 2
    finally:
        release.set()
        coordinator.close()


def test_crash_after_admission_replays_request_slots_once_and_resume_drains_inbox(tmp_path):
    from agentbench.cli.sessions.reuse_queue import requests
    from agentbench.harness.session.admission import admit_reuse_request
    from agentbench.runtime.contracts.execution import RunControl
    source, _ = original_suite(tmp_path)
    runner, factory = runner_for(tmp_path)
    options = dict(control=RunControl(), selection={('agent-0', 1)}, environ={}, root=None,
                   model=None, max_steps=None, runner=runner, suite_id=None)
    first, lease, _ = reuse_pool._reserve(source, command_id='before-crash', **options)
    second, guest, _ = reuse_pool._reserve(source, command_id='during-crash', **options)
    assert guest is None and first == second
    try:
        queued = next(value for _, value in requests(first) if value['slots'] is None)
        with SuiteStore.open(first) as store:
            slots = admit_reuse_request(store, queued)
            assert slots == [('agent-0', 1)]
            # Simulate a crash after the event write, before the inbox acknowledgment.
            assert admit_reuse_request(store, queued) == slots
            assert store.snapshot()['counts']['planned'] == 2
    finally:
        lease.close()
    outcome = recovery.execute_recovery(first, environ={}, runner=runner)
    assert outcome.passed and len(factory.executed) == 2 and factory.generated == []
    assert read_snapshot(first)['counts']['completed'] == 2
    assert all(request['slots'] is not None for _, request in requests(first))
    # A stale active index does not reopen the finished batch for a new command.
    next_run = reuse.execute_reuse(source, environ={}, runner=runner_for(tmp_path)[0], selection={('agent-0', 1)})
    assert next_run.directory != first


def test_request_racing_with_batch_completion_enters_the_next_batch(tmp_path, monkeypatch):
    source, _ = original_suite(tmp_path)
    runner, factory = runner_for(tmp_path)
    original = reuse_pool.unfinished_slots
    admitted = []
    def at_finish(store):
        selection = original(store)
        if not selection and not admitted:
            # This request waits on the same admission lock while completion is committed.
            entered = threading.Event()
            def submit():
                entered.set()
                return reuse.execute_reuse(source, environ={}, runner=runner_for(tmp_path)[0],
                    selection={('agent-0', 1)}, command_id='finish-race')
            pool = ThreadPoolExecutor(1)
            future = pool.submit(submit)
            admitted.append((pool, future))
            assert entered.wait(2)
        return selection
    monkeypatch.setattr(reuse_pool, 'unfinished_slots', at_finish)
    first = reuse.execute_reuse(source, environ={}, runner=runner, selection={('agent-0', 1)})
    pool, future = admitted[0]
    try:
        second = future.result(timeout=8)
        assert second.directory != first.directory
        assert second.result.passed and first.result.passed
        assert read_snapshot(first.directory)['counts']['planned'] == 1
        assert read_snapshot(second.directory)['counts']['planned'] == 1
    finally:
        pool.shutdown()


def test_request_journal_written_before_inbox_can_be_completed_on_retry(tmp_path, monkeypatch):
    source, _ = original_suite(tmp_path)
    runner, factory = runner_for(tmp_path)
    original = reuse_pool._queue
    def interrupted(*_):
        raise OSError('simulated interrupted inbox publication')
    monkeypatch.setattr(reuse_pool, '_queue', interrupted)
    with pytest.raises(OSError, match='publication'):
        reuse.execute_reuse(source, environ={}, runner=runner, selection={('agent-0', 1)}, command_id='partial')
    monkeypatch.setattr(reuse_pool, '_queue', original)
    result = reuse.execute_reuse(source, environ={}, runner=runner, selection={('agent-0', 1)}, command_id='partial')
    assert result.result.passed and len(factory.executed) == 1
    assert read_snapshot(result.directory)['counts']['planned'] == 1


def test_reuse_does_not_wait_behind_running_recovery_on_source_controller(tmp_path, monkeypatch):
    source, _ = original_suite(tmp_path)
    entered, release = threading.Event(), threading.Event()
    def recover(*args, **kwargs):
        entered.set()
        assert release.wait(8)
    monkeypatch.setattr(control, 'execute_recovery', recover)
    runner, factory = runner_for(tmp_path)
    monkeypatch.setattr(reuse, 'build_saved_runner', lambda *_: runner)
    coordinator = control.SuiteControl(source / 'events.json', {})
    try:
        coordinator.submit({'command_id': 'recovery', 'action': 'resume'}, coordinator.token)
        assert entered.wait(5)
        coordinator.submit({'command_id': 'parallel-reuse', 'action': 'reuse', 'agent_id': 'agent-0',
                            'case_index': 1}, coordinator.token)
        until(lambda: next(c for c in coordinator.commands if c['command_id'] == 'parallel-reuse')['status'] == 'completed')
        assert len(factory.executed) == 1
    finally:
        release.set()
        coordinator.close()
