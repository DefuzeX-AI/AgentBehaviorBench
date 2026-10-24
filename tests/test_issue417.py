"""#417: a model call that ends shortly after the Agent exits must not reject the Case."""

import threading
from types import SimpleNamespace

import pytest

from agentbench.runtime.contracts.execution import RunControl, RuntimeLimits
from agentbench.runtime.docker.runtime import DockerRuntime, DockerRuntimeError
from agentbench.runtime.interception.trace import InterceptionTraceState, TraceEvent


def emit(state, name, call='late', **data):
    state.emit(TraceEvent(name, {'call_id': call, **data}))


def callback(state, seconds):
    runtime = SimpleNamespace(control=RunControl(), _limits=RuntimeLimits(trace_drain_seconds=seconds))
    return DockerRuntime._trace_validation_callback(runtime, state)


@pytest.mark.parametrize('terminal', [
    ('llm_response', {'status': 200}),
    ('llm_error', {'error_code': 'transport_error'}),
])
def test_call_terminated_after_two_seconds_is_drained(terminal):
    state = InterceptionTraceState()
    emit(state, 'llm_request')
    name, data = terminal
    timer = threading.Timer(2.5, emit, (state, name), data)
    timer.start()
    try:
        callback(state, 10)(0)
    finally:
        timer.cancel()
    assert 'unfinished=0' in state.diagnostic()


def test_genuinely_hung_call_still_fails_after_drain_window():
    state = InterceptionTraceState()
    emit(state, 'llm_request')
    with pytest.raises(DockerRuntimeError, match='Model trace is incomplete'):
        callback(state, 0.05)(0)


def test_drain_window_is_configurable_and_validated():
    assert RuntimeLimits().trace_drain_seconds == 30
    assert RuntimeLimits.from_environment({'ABB_TRACE_DRAIN_TIMEOUT_SEC': '5'}).trace_drain_seconds == 5
    for value in ('0', '-1', 'inf', 'soon'):
        with pytest.raises(ValueError, match='ABB_TRACE_DRAIN_TIMEOUT_SEC'):
            RuntimeLimits.from_environment({'ABB_TRACE_DRAIN_TIMEOUT_SEC': value})
