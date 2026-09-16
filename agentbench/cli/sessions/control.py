"""Bound local Viewer commands; HTTP threads never execute Agent work."""

from collections.abc import Mapping
from pathlib import Path
import secrets
import threading
from queue import Queue

from agentbench.harness.session import SuiteLockedError, read_snapshot
from agentbench.observe.store import redact
from agentbench.runtime.contracts.execution import RunControl
from .recovery import execute_recovery

_CONTROLS = {}
_LOCK = threading.Lock()


def get_control(result_log):
    with _LOCK:
        return _CONTROLS.get(str(Path(result_log).resolve()))


def register_control(result_log, environ):
    path = Path(result_log).resolve()
    if path.name != 'events.json' or not (path.parent / 'plan.json').is_file():
        return None
    with _LOCK:
        control = _CONTROLS.get(str(path))
        if control is None:
            control = SuiteControl(path, environ)
            _CONTROLS[str(path)] = control
        return control


def close_control(result_log):
    """Release the coordinator owned by a Viewer, including queued commands."""
    controller = get_control(result_log)
    if controller is not None:
        controller.close()


class SuiteControl:
    """Serialize idempotent recovery commands and expose only bound capabilities."""

    def __init__(self, path, environ):
        self.path, self.environ = path, dict(environ)
        self.suite_id = read_snapshot(path.parent)['suite_id']
        self.token = secrets.token_urlsafe(32)
        self._commands, self._guard, self._queue = {}, threading.Lock(), Queue()
        self._selections = {}
        self._signals = {}
        self._stop = threading.Event()
        self._runner = None
        self._thread = threading.Thread(target=self._work, name=f'abb-control-{self.suite_id}', daemon=True)
        self._thread.start()

    @property
    def capabilities(self):
        return {'can_control': not self._stop.is_set(), 'control_url': f'/api/suites/{self.suite_id}/commands',
                'control_token': self.token}

    @property
    def commands(self):
        with self._guard:
            return [dict(item) for item in self._commands.values()]

    def submit(self, payload, token, *, origin_valid=True):
        """Validate a bound command and queue it; duplicates reuse the same acknowledgment."""
        if not origin_valid or not isinstance(token, str) or not secrets.compare_digest(token, self.token):
            raise PermissionError('Viewer control authorization failed')
        if not isinstance(payload, Mapping) or set(payload) - {
                'command_id', 'action', 'agent_id', 'case_index', 'expected_revision'}:
            raise ValueError('Unsupported Suite command fields')
        identifier = payload.get('command_id')
        if not isinstance(identifier, str) or not 1 <= len(identifier) <= 100:
            raise ValueError('A bounded command_id is required')
        action = payload.get('action')
        if action not in {'resume', 'retry'}:
            raise ValueError('Unsupported Suite action')
        with self._guard:
            if identifier in self._commands:
                return dict(self._commands[identifier])
            if self._stop.is_set():
                raise RuntimeError('This Suite controller has stopped')
            snapshot = read_snapshot(self.path.parent)
            history = snapshot.get('commands', [])
            for previous in history.values() if isinstance(history, dict) else history:
                if previous.get('command_id') == identifier:
                    return previous
            expected = payload.get('expected_revision')
            if expected is not None and (type(expected) is not int or expected != snapshot['revision']):
                raise RuntimeError('Suite changed; refresh its state before scheduling recovery')
            selection = None
            if action == 'retry':
                agent, index = payload.get('agent_id'), payload.get('case_index')
                if type(index) is not int:
                    raise ValueError('Retry requires an integer Case index')
                case = next((case for job in snapshot['jobs'] if job['agent_id'] == agent
                             for case in job['cases'] if case['case_index'] == index), None)
                if case is None or case['execution_status'] in {'completed', 'running', 'retrying', 'retry_wait'}:
                    raise ValueError('Only an unfinished inactive Case may be retried')
                selection = {(agent, index)}
            for previous_id, previous in self._commands.items():
                if previous['status'] in {'queued', 'running'}:
                    other = self._selections[previous_id]
                    if selection is None or other is None or selection.intersection(other):
                        raise RuntimeError('Recovery for this selection is already queued or running')
            command = {'command_id': identifier, 'action': action, 'status': 'queued'}
            self._commands[identifier] = command
            self._selections[identifier] = selection
            # Cancellation exists before runner construction and survives that race.
            self._signals[identifier] = RunControl()
            self._queue.put((identifier, selection, action == 'retry'))
            return dict(command)

    def _work(self):
        while True:
            item = self._queue.get()
            if item is None:
                return
            identifier, selection, replay = item
            while not self._stop.is_set():
                try:
                    execute_recovery(self.path.parent, environ=self.environ, selection=selection,
                                     replay=replay, command_id=identifier,
                                     run_control=self._signals[identifier],
                                     on_runner=lambda runner: self._set_active(identifier, runner))
                except SuiteLockedError:
                    self._stop.wait(0.2)
                    continue
                except Exception as exc:
                    from agentbench.harness.session.plan import environment_secrets
                    self._set_status(identifier, 'rejected', redact(str(exc), environment_secrets(self.environ)))
                else:
                    self._set_status(identifier, 'completed')
                break

    def _set_runner(self, runner):
        self._runner = runner

    def _set_active(self, identifier, runner):
        self._set_runner(runner)
        if runner is not None:
            self._set_status(identifier, 'running')
            if self._stop.is_set():
                runner.cancel()

    def _set_status(self, identifier, status, error=None):
        with self._guard:
            self._commands[identifier].update(status=status, error=error)

    def close(self):
        self._stop.set()
        with self._guard:
            for signal in self._signals.values():
                signal.cancel()
            for command in self._commands.values():
                if command['status'] == 'queued':
                    command.update(status='rejected', error='Viewer recovery controller was closed')
        if self._runner is not None:
            self._runner.cancel()
        self._queue.put(None)
        with _LOCK:
            if _CONTROLS.get(str(self.path)) is self:
                del _CONTROLS[str(self.path)]
        if self._thread is not threading.current_thread():
            self._thread.join(timeout=60)
