"""Real controller idempotency and queued recovery without paid SDK requests."""

import threading

import pytest

from agentbench.cli.sessions import control as module
from agentbench.cli.viewer_control import controlled_snapshot
from agentbench.harness.registry import AgentRegistration
from agentbench.harness.session import SuiteStore, read_snapshot


@pytest.fixture
def suite_path(tmp_path):
    source = tmp_path / 'agent'
    source.mkdir()
    (source / 'agent.py').write_text('def run(value): return value\n')
    agent = AgentRegistration('agent', source, True, 'ready', 'test', 'test', 2)
    with SuiteStore.begin(tmp_path / 'suites', 'suite_control', [agent]) as store:
        return store.path


def test_real_controller_retries_writer_lock_and_deduplicates_command(suite_path, monkeypatch):
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    calls = []

    def recover(directory, **kwargs):
        with SuiteStore.open(directory) as store:
            calls.append((threading.get_ident(), kwargs['selection'], kwargs['replay']))
            entered.set()
            assert release.wait(2)
            store.append({'event': 'suite_resumed', 'command_id': kwargs['command_id'], 'status': 'completed'})
            finished.set()

    monkeypatch.setattr(module, 'execute_recovery', recover)
    controller = module.SuiteControl(suite_path, {})
    payload = {'command_id': 'one', 'action': 'retry', 'agent_id': 'agent', 'case_index': 0}
    try:
        with SuiteStore.open(suite_path.parent):
            assert controller.submit(payload, controller.token)['status'] == 'queued'
            assert controller.submit(payload, controller.token)['command_id'] == 'one'
            assert not entered.wait(0.05)
        assert entered.wait(2)
        assert controller.submit(payload, controller.token)['command_id'] == 'one'
        release.set()
        assert finished.wait(2)
        assert len(calls) == 1
        assert calls[0][0] != threading.get_ident()
        assert calls[0][1:] == ({('agent', 0)}, True)
        assert read_snapshot(suite_path.parent)['commands'][0]['command_id'] == 'one'
    finally:
        release.set()
        controller.close()
        controller._thread.join(timeout=2)


def test_controller_errors_overlay_without_case_revision_change(suite_path, monkeypatch):
    failed = threading.Event()

    def reject(*args, **kwargs):
        failed.set()
        raise ValueError('Source configuration changed')

    monkeypatch.setattr(module, 'execute_recovery', reject)
    controller = module.SuiteControl(suite_path, {})
    from agentbench.cli import viewer_control
    monkeypatch.setattr(viewer_control, 'bound_controller', lambda path: controller)
    try:
        before = read_snapshot(suite_path.parent)
        controller.submit({'command_id': 'rejected', 'action': 'resume'}, controller.token)
        assert failed.wait(2)
        controller.close()
        controller._thread.join(timeout=2)
        result = controlled_snapshot(before, suite_path)
        assert result['revision'] == before['revision']
        assert result['commands'][0]['status'] == 'rejected'
        assert result['commands'][0]['error'] == 'Source configuration changed'
    finally:
        controller.close()


def test_real_controller_rejects_unbound_token_and_arbitrary_fields(suite_path):
    controller = module.SuiteControl(suite_path, {})
    try:
        with pytest.raises(PermissionError, match='authorization'):
            controller.submit({'command_id': 'one', 'action': 'resume'}, 'wrong-token')
        with pytest.raises(ValueError, match='Unsupported'):
            controller.submit({'command_id': 'one', 'action': 'resume', 'shell': 'anything'}, controller.token)
        assert controller.commands == []
    finally:
        controller.close()
        controller._thread.join(timeout=2)
