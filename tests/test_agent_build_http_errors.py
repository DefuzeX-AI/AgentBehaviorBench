"""HTTP diagnostics retain upstream reasons without exposing credentials/bodies."""

import io
import json
from types import SimpleNamespace
from urllib.error import HTTPError
from http.client import IncompleteRead

import pytest

from agentbench.onboarding.build_agent_env.common.errors import BuildError
from tests.test_agent_build_client import client, generate
from tests.agent_build_fixtures import source, plan, build


def reject(instance, body, *, stream=None):
    response = stream if stream is not None else io.BytesIO(body)

    def fail(*args, **kwargs):
        raise HTTPError("https://example.invalid", 400, "untrusted status text", {}, response)

    instance.opener = SimpleNamespace(open=fail)
    with pytest.raises(BuildError) as caught:
        generate(instance, {})
    assert response.closed
    return str(caught.value)


def test_wrapped_provider_error_explains_schema_failure_without_dumping_metadata():
    body = {"error": {"message": "Provider returned error", "code": 400,
                      "metadata": {"provider_name": "OpenAI", "raw": json.dumps({"error": {
                          "message": "Invalid schema: 'if' is not permitted.",
                          "type": "invalid_request_error", "param": "response_format",
                          "request": "PRIVATE_REQUEST_BODY"}}), "headers": {"cookie": "PRIVATE_COOKIE"}}}}
    message = reject(client(), json.dumps(body).encode())
    assert "OpenRouter HTTP 400" in message
    assert "Invalid schema: 'if' is not permitted." in message
    assert "OpenAI" in message and "response_format" in message
    assert "PRIVATE_REQUEST_BODY" not in message and "PRIVATE_COOKIE" not in message
    assert "earlier completed files remain saved" in message


def test_message_redacts_known_keys_inline_credentials_and_terminal_controls():
    body = {"error": {"message": (
        "Bad request test-credential-never-log; Authorization: Bearer arbitrary-token; "
        'api_key="another-unknown-key"; password=secret123; '
        "https://user:password@example.invalid/path; \x1b[31mInvalid schema\x1b[0m\nRetry later")}}
    message = reject(client(), json.dumps(body).encode())
    assert "Invalid schema" in message and "[REDACTED]" in message
    for secret in ("test-credential-never-log", "arbitrary-token", "another-unknown-key", "secret123", "user:password"):
        assert secret not in message
    assert "\x1b" not in message and "\n" not in message


@pytest.mark.parametrize("body", [b"private unstructured response", b"<html>private proxy response</html>",
                                  b'{"error":null}', b'{"error":{"message":[]}}', b"\xff", b""])
def test_unusable_body_preserves_status_without_dumping_server_text(body):
    message = reject(client(), body)
    assert "OpenRouter HTTP 400" in message
    assert "private" not in message and "untrusted" not in message


@pytest.mark.parametrize("failure", [OSError("PRIVATE_READ_ERROR"), IncompleteRead(b"PRIVATE_READ_ERROR")])
def test_error_read_failure_does_not_hide_original_http_status(failure):
    class Unreadable(io.BytesIO):
        def read(self, *args):
            raise failure

    message = reject(client(), b"", stream=Unreadable())
    assert "OpenRouter HTTP 400" in message and "PRIVATE_READ_ERROR" not in message


def test_oversized_error_body_is_not_partially_logged():
    class Recording(io.BytesIO):
        requested = None

        def read(self, size=-1):
            self.requested = size
            return super().read(size)

    stream = Recording(json.dumps({"error": {"message": "PRIVATE" * 5000}}).encode())
    message = reject(client(max_response_bytes=256), b"", stream=stream)
    assert 0 < stream.requested <= 257
    assert "PRIVATE" not in message and "OpenRouter HTTP 400" in message


def test_display_limit_is_applied_after_redaction():
    text = "Invalid schema. " + "x" * 1400 + "test-credential-never-log" + "z" * 2000
    message = reject(client(), json.dumps({"error": {"message": text}}).encode())
    assert message.startswith("OpenRouter HTTP 400: Invalid schema.")
    assert len(message) < 1900
    assert "test-credential" not in message and "truncated" in message


def test_build_failure_records_preserve_sanitized_provider_reason(source, plan):
    instance = client()

    def fail(*args, **kwargs):
        body = {"error": {"message": "Invalid schema for response_format; key=test-credential-never-log"}}
        raise HTTPError("https://example.invalid", 400, "private", {}, io.BytesIO(json.dumps(body).encode()))

    instance.opener = SimpleNamespace(open=fail)
    with pytest.raises(BuildError, match="Invalid schema for response_format"):
        build(source, plan, client=instance)
    from agentbench.onboarding.build_agent_env.common.records import records_directory
    records = records_directory(source.directory, source.directory.parents[1] / "registry.toml")
    record = json.loads(next(records.glob("*/build-result.json")).read_text())
    assert record["status"] == "failed" and record["completed_files"] == []
    assert "Invalid schema for response_format" in record["message"]
    assert "[REDACTED]" in record["message"] and "test-credential-never-log" not in record["message"]
