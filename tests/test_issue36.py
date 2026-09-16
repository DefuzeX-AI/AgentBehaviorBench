"""Issue #36: observed transport failures are terminal evidence, not missing capture."""
import pytest

from agentbench.runtime.interception.trace import InterceptionTraceState, TraceEvent


def send(state, event, call_id, **data):
    state.emit(TraceEvent(event, {'call_id': call_id, **data}))


@pytest.mark.parametrize('code', ['transport_error', 'upstream_error'])
def test_observed_failure_does_not_erase_completed_calls(code):
    state = InterceptionTraceState()
    send(state, 'llm_request', 'ok')
    send(state, 'llm_response', 'ok')
    send(state, 'llm_request', 'ended')
    send(state, 'llm_error', 'ended', error_code=code, error_stage='transport')
    assert state.wait_for_completion_after(0, timeout=0)
    assert state.wait_for_idle(timeout=.02, quiet=0)


@pytest.mark.parametrize('code', [None, 'egress_denied', 'authentication_failed',
    'request_preparation_failed', 'response_conversion_failed', 'stream_processing_failed'])
def test_policy_and_capture_errors_remain_rejected(code):
    state = InterceptionTraceState()
    send(state, 'llm_request', 'a')
    send(state, 'llm_response', 'a')
    send(state, 'llm_error', 'a', error_code=code)
    assert not state.wait_for_completion_after(0, timeout=0)
    assert not state.wait_for_idle(timeout=.02, quiet=0)


def test_truly_unfinished_call_still_rejected():
    state = InterceptionTraceState()
    send(state, 'llm_request', 'missing')
    assert not state.wait_for_completion_after(0, timeout=0)
    assert not state.wait_for_idle(timeout=.002, quiet=0)
