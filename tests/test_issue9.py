"""Issue #9: denied endpoints retain diagnostic identity without query secrets."""
from pathlib import Path


def test_failure_preserves_source_and_target_as_distinct_endpoints(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(root/'agentbench/services/model-interceptor/src'))
    from defuzex_model_interceptor.error.failure import InterceptionFailure, ErrorCode
    event = InterceptionFailure(code=ErrorCode.UPSTREAM_ERROR, message='Rejected', call_id='actual-call',
        source_host='api.openai.com', source_path='/v1/chat/completions?key=synthetic-secret',
        target_host='openrouter.ai', target_path='/api/v1/chat/completions#synthetic-secret',
        method='POST', upstream_status=401).to_event_fields()
    assert event['source_host'] == 'api.openai.com'
    assert event['target_host'] == 'openrouter.ai'
    assert event['upstream_status'] == 401
    assert event['call_id'] == 'actual-call'
    assert event['error_stage'] == 'upstream'
    assert event['source_path'] == '/v1/chat/completions'
    assert event['target_path'] == '/api/v1/chat/completions'
