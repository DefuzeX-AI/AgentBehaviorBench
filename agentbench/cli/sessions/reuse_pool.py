"""Coordinate compatible live reuse batches across CLI and Viewer processes."""

from contextlib import contextmanager
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import time
from uuid import uuid4

from agentbench.harness.result import BenchmarkSuiteResult, SuiteAgentResult
from agentbench.harness.session import SuiteStore, read_snapshot
from agentbench.harness.session.store import read_suite
from agentbench.harness.session.admission import agent_identity
from agentbench.harness.session.atomic import atomic_json
from agentbench.harness.session.cases import retain_prepared
from agentbench.harness.session.codec import case_from_json, json_value
from agentbench.harness.session.locking import SuiteLock, SuiteLockedError
from agentbench.harness.session.plan import digest_json, environment_secrets, registration_record
from agentbench.runtime.contracts.execution import RunControl

from . import reuse
from .configuration import build_saved_runner
from .log import SuiteResultLog
from .recovery import execute_in_store
from .reuse_queue import admit_waiting, requests, unfinished_slots


@contextmanager
def pool_guard(control):
    lock = SuiteLock(reuse.PROJECT_ROOT / 'cache/reuse-pool/guard')
    deadline = time.monotonic() + 30
    while True:
        control.check()
        try:
            lock.acquire()
            break
        except SuiteLockedError:
            if time.monotonic() >= deadline:
                raise RuntimeError('Reuse admission is busy; retry this request')
            control.wait(0.05)
    try:
        yield
    finally:
        lock.close()


def acquire_owner(directory):
    lease = SuiteLock(directory / '.reuse-owner')
    try:
        lease.acquire()
    except SuiteLockedError:
        return None
    return lease


def result_snapshot(directory):
    snapshot = read_snapshot(directory)
    items = tuple(SuiteAgentResult(job['agent_id'], tuple(case_from_json(case['result'])
        for case in job['cases'] if case['result'] is not None), len(job['cases'])) for job in snapshot['jobs'])
    return BenchmarkSuiteResult(snapshot['suite_id'], tuple(job['agent_id'] for job in snapshot['jobs']), items)


def _active_path(directory):
    key = hashlib.sha256(str(directory).encode()).hexdigest()
    return reuse.PROJECT_ROOT / 'cache/reuse-pool/active' / f'{key}.json'


def _publish_owner(directory, environ):
    plan, _ = read_suite(directory)
    agents = {record['agent_id']: record for record in plan['agents']}
    for _, request in requests(directory):
        for record in request['agents']:
            agents.setdefault(record['agent_id'], record)
    atomic_json(_active_path(directory), {'directory': str(directory), 'configuration': plan['configuration'],
        'credentials': digest_json(sorted(environment_secrets(environ))), 'agents': list(agents.values())})


def _compatible(active, inputs, agents, root, credentials):
    existing = {record['agent_id']: agent_identity(record) for record in active['agents']}
    return (active['configuration'] == inputs.configuration and active['credentials'] == credentials
            and (root is None or Path(active['directory']).parent == Path(root).resolve())
            and all(record['agent_id'] not in existing or existing[record['agent_id']] == agent_identity(record)
                    for record in agents))


def _queue(directory, record, inputs, agents):
    path = directory / 'reuse-requests' / record['request_id'] / 'request.json'
    if path.is_file():
        return
    entries = []
    for agent_id, index, case in inputs.originals:
        # The inbox owns a copy before acknowledgment, even while the writer is busy.
        saved = retain_prepared(path.parent, agent_id, replace(case, case_index=index))
        entries.append({'agent_id': agent_id, 'prepared_case': json_value(saved), 'origin': {
            'suite_id': inputs.plan['suite_id'], 'revision': inputs.snapshot['revision'],
            'agent_id': agent_id, 'case_index': case.case_index, 'case_id': case.case_id,
            'artifact_sha256': case.artifact_sha256, 'content_sha256': case.content_sha256}})
    atomic_json(path, {**record, 'agents': agents, 'cases': entries, 'status': 'queued',
        'slots': [(agent, index) for agent, index, _ in inputs.originals] if record['initial'] else None})


def _reserve(source, *, control, command_id, selection, environ, root, model, max_steps, runner, suite_id):
    key = hashlib.sha256(f'{source}\0{command_id}'.encode()).hexdigest()
    journal = reuse.PROJECT_ROOT / 'cache/reuse-pool/requests' / f'{key}.json'
    intent = {'source': str(source), 'selection': None if selection is None else sorted(map(list, selection)),
              'root': None if root is None else str(Path(root).resolve()), 'model': model, 'max_steps': max_steps,
              'suite_id': suite_id}
    # Cheap duplicate delivery must not rebuild a runner or require old source bytes.
    with pool_guard(control):
        if journal.is_file():
            record = json.loads(journal.read_text())
            if record['intent'] != intent:
                raise ValueError('Saved reuse destination does not match this command')
            directory = Path(record['directory'])
            if (directory / 'reuse-requests' / key / 'request.json').is_file():
                lease = acquire_owner(directory)
                if lease is not None and read_snapshot(directory)['state'] != 'complete':
                    try:
                        _publish_owner(directory, environ)
                    except BaseException:
                        lease.close()
                        raise
                return directory, lease, runner
    inputs = reuse.reuse_inputs(source, environ=environ, model=model, max_steps=max_steps,
                                runner=runner, selection=selection)
    agents = [registration_record(agent) for agent in inputs.registrations]
    credentials = digest_json(sorted(environment_secrets(environ)))
    with pool_guard(control):
        # Another delivery may have published the same request during validation.
        record = json.loads(journal.read_text()) if journal.is_file() else None
        if record and record['intent'] != intent:
            raise ValueError('Saved reuse destination does not match this command')
        directory, lease = (Path(record['directory']), None) if record else (None, None)
        if directory is None and suite_id is None:
            for path in sorted((reuse.PROJECT_ROOT / 'cache/reuse-pool/active').glob('*.json')):
                try:
                    active = json.loads(path.read_text())
                    compatible = _compatible(active, inputs, agents, root, credentials)
                except (OSError, ValueError, KeyError, TypeError):
                    continue
                if not compatible:
                    continue
                candidate = Path(active['directory'])
                if not (candidate / 'plan.json').is_file():
                    path.unlink(missing_ok=True)
                    continue
                probe = acquire_owner(candidate)
                if probe is not None:
                    probe.close()
                    path.unlink(missing_ok=True)  # An inactive owner cannot accept new work.
                    continue
                directory = candidate
                break
        initial = directory is None
        if initial:
            identifier = suite_id or f'suite_reuse_{key[:32]}'
            directory = (Path(root).resolve() if root is not None else source.parent) / identifier
            if not directory.exists():
                reuse.create_reuse(inputs, environ=environ, root=directory.parent, suite_id=identifier)
            else:
                if suite_id is not None:
                    raise FileExistsError('Suite already exists; open it for recovery')
                # Recover publication interrupted before the request journal was written.
                snapshot = read_snapshot(directory)
                origins = {(case.get('origin', {}).get('agent_id'), case.get('origin', {}).get('case_index'))
                           for job in snapshot['jobs'] for case in job['cases']}
                expected = {(agent, case.case_index) for agent, _, case in inputs.originals}
                if snapshot['origin_suite_id'] != inputs.plan['suite_id'] or origins != expected:
                    raise ValueError('Saved reuse destination does not match this command')
        if record is None:
            record = {'request_id': key, 'directory': str(directory), 'intent': intent, 'initial': initial,
                      'received_at_ns': time.time_ns()}
            atomic_json(journal, record)
        _queue(directory, record, inputs, agents)
        lease = acquire_owner(directory)
        active_path = _active_path(directory)
        if lease is not None:
            current_agents = agents
        else:
            current_agents = json.loads(active_path.read_text())['agents']
            known = {agent['agent_id'] for agent in current_agents}
            current_agents += [agent for agent in agents if agent['agent_id'] not in known]
        try:
            atomic_json(active_path, {'directory': str(directory), 'configuration': inputs.configuration,
                                     'credentials': credentials, 'agents': current_agents})
        except BaseException:
            if lease is not None:
                lease.close()
            raise
        return directory, lease, inputs.runner


def _drive(directory, lease, *, runner, environ, control, on_event, on_runner):
    try:
        with SuiteStore.open(directory, environ=environ) as store:
            while True:
                control.check()
                # Closing admission and declaring completion use the same lock as enqueue.
                with pool_guard(control):
                    admit_waiting(store)
                    selection = unfinished_slots(store)
                    if not selection:
                        result = result_snapshot(directory)
                        if store.snapshot()['state'] != 'complete':
                            SuiteResultLog(store).append_suite_complete(result)
                        _active_path(directory).unlink(missing_ok=True)
                        return result
                runner = runner or build_saved_runner(store.plan['configuration'], environ)
                execute_in_store(store, environ=environ, runner=runner, selection=selection,
                    on_event=on_event, on_runner=on_runner, run_control=control,
                    on_tick=lambda: admit_waiting(store), finalize=False)
    finally:
        try:
            _active_path(directory).unlink(missing_ok=True)
        finally:
            lease.close()


def execute_pooled_reuse(directory, *, environ, root=None, model=None, max_steps=None, runner=None,
                         suite_id=None, on_created=None, on_event=None, run_control=None,
                         selection=None, on_runner=None, command_id=None):
    control = run_control or RunControl()
    control.check()
    directory, lease, runner = _reserve(Path(directory).resolve(), control=control,
        command_id=command_id or uuid4().hex, selection=selection, environ=environ,
        root=root, model=model, max_steps=max_steps, runner=runner, suite_id=suite_id)
    try:
        if on_created:
            on_created(directory)
        if lease is not None:
            result = _drive(directory, lease, runner=runner, environ=environ, control=control,
                            on_event=on_event, on_runner=on_runner)
            lease = None
        else:
            while True:
                control.check()
                probe = acquire_owner(directory)
                if probe is not None:
                    probe.close()
                    if read_snapshot(directory)['state'] != 'complete':
                        raise RuntimeError(f'Reuse Suite interrupted; resume {directory.name}')
                    result = result_snapshot(directory)
                    break
                control.wait(0.1)
        return reuse.ReuseExecution(directory, result)
    finally:
        if lease is not None:
            lease.close()
