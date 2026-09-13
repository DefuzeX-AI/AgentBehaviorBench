"""The error wire contract works without importing mitmproxy."""
import json

import pytest

from defuzex_model_interceptor.observation.events import failure_fields
from defuzex_model_interceptor.error import ErrorCode, InterceptionFailure, RequestKind


def test_failure_serialization_redacts_all_fields_and_omits_url_queries():
    failure = InterceptionFailure(
        code=ErrorCode.UPSTREAM_ERROR, message="Rejected real-secret", call_id="call-1",
        request_kind=RequestKind.MODEL, source_host="api.example.com", source_port=8443,
        source_path="/real-secret/messages?key=hidden-query",
        target_path="/chat?token=hidden-target", upstream_status=429, local_status=429,
    )
    fields = json.loads(json.dumps(failure_fields(failure, ("real-secret",))))
    assert fields["error"] == "Rejected [REDACTED]"
    assert fields["source_path"] == "/[REDACTED]/messages"
    assert fields["target_path"] == "/chat"
    assert fields["source_port"] == 8443
    assert fields["upstream_status"] == fields["local_status"] == 429
    assert fields["request_kind"] == "model"
    assert fields["error_code"] == "upstream_error"
    assert fields["error_stage"] == "upstream"
    assert "real-secret" not in json.dumps(fields)
    # Sanitizing the wire representation does not mutate the evidence object.
    assert failure.message == "Rejected real-secret"


@pytest.mark.parametrize("code,stage", [
    (ErrorCode.EGRESS_DENIED, "policy"),
    (ErrorCode.AUTHENTICATION_FAILED, "authentication"),
    (ErrorCode.REQUEST_PREPARATION_FAILED, "request_preparation"),
    (ErrorCode.UPSTREAM_ERROR, "upstream"),
    (ErrorCode.RESPONSE_CONVERSION_FAILED, "response_conversion"),
    (ErrorCode.STREAM_PROCESSING_FAILED, "stream_processing"),
    (ErrorCode.TRANSPORT_ERROR, "transport"),
])
def test_failure_codes_have_stable_stages_without_inventing_upstream_evidence(code, stage):
    fields = InterceptionFailure(code, "failed", "call-1").to_event_fields()
    assert fields["error_stage"] == stage
    assert fields["upstream_status"] is None
    assert fields["target_host"] is None
    assert fields["request_kind"] == "unknown"
