"""Coordinator-owned persistent Suite plan and ordered event log."""

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
from uuid import uuid4

from agentbench.observe.store import redact

from .atomic import atomic_json
from .cases import retain_prepared, verify_prepared
from .codec import case_from_json, event_to_json, prepared_from_json
from .locking import SuiteLock
from .plan import (build_plan, environment_secrets, registrations_from_plan,
                   validate_plan, validate_provenance, validate_suite_id)
from .snapshot import suite_snapshot

EVENT_SCHEMA = 'abb.suite.event.v1'


def suite_directory(root, suite_id=None):
    directory = Path(root).resolve()
    return directory if suite_id is None else directory / validate_suite_id(suite_id)


def read_suite(directory):
    """Read atomic files without taking a writer lock; suitable for live viewers."""
    directory = Path(directory)
    plan = validate_plan(json.loads((directory / 'plan.json').read_text(encoding='utf-8')))
    events = json.loads((directory / 'events.json').read_text(encoding='utf-8'))
    if not isinstance(events, list):
        raise ValueError('Suite events must be an array')
    for index, event in enumerate(events, 1):
        if (not isinstance(event, dict) or event.get('schema') != EVENT_SCHEMA
                or event.get('sequence') != index or event.get('suite_id') != plan['suite_id']):
            raise ValueError('Suite events have inconsistent schema, sequence or identity')
    return plan, events


def read_snapshot(directory):
    return suite_snapshot(*read_suite(directory))


class SuiteStore:
    """Exclusive Suite writer; close it after coordination and resource cleanup.

    ``begin`` and ``open`` acquire the operating-system lock before returning.
    Use the result as a context manager or call ``close`` explicitly. Readers use
    ``read_snapshot`` and never acquire this lock. Only the creating coordinator
    thread may mutate it; worker callbacks must cross the existing EventBus.
    """

    def __init__(self, directory, *, environ=None):
        self.directory = Path(directory).resolve()
        self.path = self.directory / 'events.json'
        self._secrets = environment_secrets(environ)
        self._lock = SuiteLock(self.directory)
        self._owner = threading.get_ident()
        self._plan, self._events = None, []

    @classmethod
    def begin(cls, root, suite_id, registrations, *, configuration=None, environ=None,
              result_log_path=None, origin_suite_id=None):
        """Persist a fixed selection before any work is admitted, returning its writer."""
        store = cls(suite_directory(root, suite_id), environ=environ)
        store._lock.acquire()
        try:
            if (store.directory / 'plan.json').exists():
                raise FileExistsError('Suite already exists; open it for recovery')
            store._plan = build_plan(suite_id, registrations, configuration=configuration,
                                     secrets=store._secrets, result_log_path=store.path,
                                     origin_suite_id=origin_suite_id)
            if result_log_path is not None:
                store._plan['requested_output_path'] = str(Path(result_log_path).resolve())
            atomic_json(store.path, [])
            atomic_json(store.directory / 'plan.json', store._plan)
            agents = store._plan['agents']
            store.append({'event': 'run_started', 'selected_agent_ids': [agent['agent_id'] for agent in agents],
                          'selected_case_counts': {agent['agent_id']: agent['case_count'] for agent in agents},
                          'total_case_count': sum(agent['case_count'] for agent in agents)})
            return store
        except BaseException:
            store.close()
            raise

    @classmethod
    def open(cls, root, suite_id=None, *, environ=None):
        """Acquire a saved Suite without dispatching or assuming interrupted work stopped."""
        directory = suite_directory(root, suite_id)
        if not (directory / 'plan.json').is_file():
            raise FileNotFoundError('Saved Suite plan does not exist')
        store = cls(directory, environ=environ)
        store._lock.acquire()
        try:
            store._plan, store._events = read_suite(directory)
            return store
        except BaseException:
            store.close()
            raise

    @property
    def suite_id(self):
        return self._plan['suite_id']

    @property
    def result_log_path(self):
        return self.path

    @property
    def plan(self):
        return deepcopy(self._plan)

    @property
    def events(self):
        return deepcopy(self._events)

    @property
    def registrations(self):
        return registrations_from_plan(self._plan)

    def _check_writer(self):
        self._lock.check()
        if self._owner != threading.get_ident():
            raise RuntimeError('Only the Suite coordinator thread may mutate persisted state')

    def append(self, event):
        """Atomically append a redacted event with a durable monotonic sequence."""
        self._check_writer()
        value = event_to_json(event)
        if value.get('suite_id', self.suite_id) != self.suite_id:
            raise ValueError('Event belongs to another Suite')
        if not isinstance(value.get('event'), str):
            raise ValueError('Suite event requires an event name')
        if value.get('agent_id') is not None:
            agent = next((item for item in self._plan['agents'] if item['agent_id'] == value['agent_id']), None)
            if agent is None:
                raise ValueError('Event refers to an Agent outside this Suite')
            index = value.get('case_index')
            if index is not None and (type(index) is not int or not 0 <= index < agent['case_count']):
                raise ValueError('Event Case index is outside the planned selection')
        value = redact({'event_id': uuid4().hex, 'timestamp': datetime.now(timezone.utc).isoformat(),
                        'source': 'abb', **value, 'schema': EVENT_SCHEMA,
                        'suite_id': self.suite_id, 'sequence': len(self._events) + 1}, self._secrets)
        pending = [*self._events, value]
        atomic_json(self.path, pending)
        self._events = pending
        return deepcopy(value)

    append_event = append

    def snapshot(self):
        return suite_snapshot(self._plan, self._events)

    def validate_provenance(self, registrations=None, configuration=None):
        validate_provenance(self._plan, self.registrations if registrations is None else registrations,
                            self._plan['configuration'] if configuration is None else configuration,
                            secrets=self._secrets)

    def retain_case(self, agent_id, case):
        """Publish immutable bytes before recording a prepared slot; return its stable ref."""
        self._check_writer()
        job = next((job for job in self.snapshot()['jobs'] if job['agent_id'] == agent_id), None)
        if job is None or not 0 <= case.case_index < len(job['cases']):
            raise ValueError('Prepared Case is outside the planned selection')
        for other in job['cases']:
            saved = other['prepared_case']
            if other['case_index'] == case.case_index or saved is None:
                continue
            if ((case.case_id is not None and saved.get('case_id') == case.case_id)
                    or (case.content_sha256 is not None and saved.get('content_sha256') == case.content_sha256)):
                raise ValueError('Prepared Case duplicates an already saved slot for this Agent')
        existing = job['cases'][case.case_index]['prepared_case']
        retained = retain_prepared(self.directory, agent_id, case, existing)
        if existing is None:
            self.append({'event': 'case_prepared', 'agent_id': agent_id,
                         'case_index': case.case_index, 'case_id': case.case_id, 'prepared_case': retained,
                         'resumable': retained.artifact_path is not None})
        return retained

    def prepared_cases(self, agent_id):
        job = next(job for job in self.snapshot()['jobs'] if job['agent_id'] == agent_id)
        return tuple(verify_prepared(prepared_from_json(case['prepared_case'])) for case in job['cases']
                     if case['prepared_case'] is not None)

    def prepared_case(self, agent_id, case_index):
        """Verify one saved slot so an unavailable file does not block its siblings."""
        job = next(job for job in self.snapshot()['jobs'] if job['agent_id'] == agent_id)
        value = job['cases'][case_index]['prepared_case']
        return None if value is None else verify_prepared(prepared_from_json(value))

    def completed_results(self, agent_id):
        """Skip completed evaluations, including Judge issue, when scheduling a resume."""
        job = next(job for job in self.snapshot()['jobs'] if job['agent_id'] == agent_id)
        return tuple(case_from_json(case['result']) for case in job['cases']
                     if case['execution_status'] == 'completed' and case['result'] is not None)

    def close(self):
        self._lock.close()

    def __enter__(self):
        self._check_writer()
        return self

    def __exit__(self, *args):
        self.close()
