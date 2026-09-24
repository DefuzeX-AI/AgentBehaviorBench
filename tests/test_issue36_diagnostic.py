"""Issue #36: a rejected trace names the call to look up, not only counts."""
from agentbench.runtime.interception.trace import InterceptionTraceState, TraceEvent


def _event(name, call_id, **data):
    return TraceEvent(name, {'call_id': call_id, **data})


def test_first_rejecting_event_is_named_with_its_code_and_source():
    state = InterceptionTraceState()
    state.emit(_event('llm_request', 'call_ok'))
    state.emit(_event('llm_response', 'call_ok'))
    state.emit(_event('llm_error', 'call_blocked', error_code='egress_denied',
                      source_host='undeclared.example', source_path='/collect',
                      error='Undeclared network request blocked'))
    state.emit(_event('llm_error', 'call_later', error_code='authentication_failed',
                      source_host='model.example', source_path='/v1/chat'))
    text = state.diagnostic()
    assert 'capture_rejected=True' in text
    # A refused non-model destination is counted, not the rejection (#137).
    assert 'egress_denied=1' in text
    assert 'first_rejection=call_later llm_error authentication_failed model.example /v1/chat' in text
    assert 'Undeclared network request blocked' not in text  # Codes and locators only, never error text.


def test_first_unfinished_call_is_named():
    state = InterceptionTraceState()
    for call in ('call_done', 'call_open_1', 'call_open_2'):
        state.emit(_event('llm_request', call))
    state.emit(_event('llm_response', 'call_done'))
    assert state.diagnostic().endswith('first_unfinished=call_open_1')


def test_transport_failures_are_observations_not_rejections():
    state = InterceptionTraceState()
    state.emit(_event('llm_request', 'call_dropped'))
    state.emit(_event('llm_error', 'call_dropped', error_code='transport_error'))
    text = state.diagnostic()
    assert 'first_rejection' not in text and 'first_unfinished' not in text
    assert 'observed_failures=1' in text and 'capture_rejected=False' in text


def test_truncated_evidence_is_named():
    state = InterceptionTraceState()
    state.emit(_event('llm_response', 'call_big', truncated=True))
    assert 'first_rejection=call_big llm_response truncated' in state.diagnostic()
