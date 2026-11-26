"""Agent trace exports are archived byte for byte before span rows are derived."""
import gzip
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from agentbench.harness.otel import create_session
from agentbench.harness.otel.config import CaptureConfig, parse_config
from agentbench.harness.otel.evidence import publish_capture

SPAN = {"name": "read", "traceId": "12" * 16, "spanId": "34" * 8, "startTimeUnixNano": "12345678901",
        "attributes": [{"key": "api_key", "value": {"stringValue": "secret-value"}}]}
BATCH = {"resourceSpans": [{"scopeSpans": [{"scope": {"name": "test"}, "spans": [SPAN]}]}]}


def protobuf_body():
    pytest.importorskip("opentelemetry.proto")
    from google.protobuf.json_format import ParseDict
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
    import base64
    span = {**SPAN, "traceId": base64.b64encode(bytes.fromhex(SPAN["traceId"])).decode(),
            "spanId": base64.b64encode(bytes.fromhex(SPAN["spanId"])).decode()}
    return ParseDict({"resourceSpans": [{"scopeSpans": [{"scope": {"name": "test"}, "spans": [span]}]}]},
                     ExportTraceServiceRequest()).SerializeToString()


def post(session, body, headers):
    request = Request(session.receiver.endpoint + "/v1/traces", body, headers)
    try:
        with urlopen(request) as response:
            return response.status
    except HTTPError as error:
        return error.code


def index(directory):
    return [json.loads(line) for line in (directory / "raw/index.jsonl").read_text().splitlines()]


def assert_owner_only(directory):
    assert (directory / "raw").stat().st_mode & 0o777 == 0o700
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in (directory / "raw").iterdir())


@pytest.mark.parametrize("case", ["json-gzip", "protobuf"])
def test_http_body_is_archived_before_decompression_and_parsing(tmp_path, case):
    session = create_session(CaptureConfig("native-otlp"), tmp_path, "example")
    try:
        if case == "json-gzip":
            body = gzip.compress(json.dumps(BATCH).encode())
            headers = {"Content-Type": "application/json", "Content-Encoding": "gzip"}
            name = "000001.json.gz"
        else:
            body = protobuf_body()
            headers = {"Content-Type": "application/x-protobuf"}
            name = "000001.pb"
        assert post(session, body, headers) == 200
    finally:
        session.close()
    assert (tmp_path / "raw" / name).read_bytes() == body
    received, accepted = index(tmp_path)
    assert received["event"] == "received" and received["sha256"] == hashlib.sha256(body).hexdigest()
    assert received["content_type"] == headers["Content-Type"]
    assert received["content_encoding"] == headers.get("Content-Encoding")
    assert accepted == {"event": "accepted", "batch": 1, "span_lines": [1, 1]}
    row = json.loads((tmp_path / "spans.jsonl").read_text())
    assert row["archive"] == {"file": f"otel/raw/{name}", "batch": 1}
    # The derived row stays redacted; only the archive keeps the original value.
    assert "secret-value" not in (tmp_path / "spans.jsonl").read_text()
    status = json.loads((tmp_path / "status.json").read_text())
    assert status["raw_batches"] == 1 and status["raw_redacted"] is False and status["span_count"] == 1
    assert_owner_only(tmp_path)


def test_grpc_message_bytes_are_archived(tmp_path):
    grpc = pytest.importorskip("grpc")
    body = protobuf_body()
    session = create_session(CaptureConfig("native-otlp", protocol="grpc"), tmp_path, "example")
    try:
        target = session.receiver.endpoint.removeprefix("http://")
        with grpc.insecure_channel(target) as channel:
            export = channel.unary_unary("/opentelemetry.proto.collector.trace.v1.TraceService/Export")
            export(body, timeout=5)
            with pytest.raises(grpc.RpcError) as invalid:
                export(b"\xff\xff", timeout=5)
            assert invalid.value.code() == grpc.StatusCode.INVALID_ARGUMENT
    finally:
        session.close()
    assert (tmp_path / "raw/000001.pb").read_bytes() == body
    assert (tmp_path / "raw/000002.pb").read_bytes() == b"\xff\xff"
    events = [(e["event"], e["batch"]) for e in index(tmp_path)]
    assert events == [("received", 1), ("accepted", 1), ("received", 2), ("rejected", 2)]
    assert json.loads((tmp_path / "spans.jsonl").read_text())["archive"]["batch"] == 1


def test_rejected_and_unsupported_requests_are_archived(tmp_path):
    session = create_session(CaptureConfig("native-otlp"), tmp_path, "example")
    try:
        assert post(session, b"{not json", {"Content-Type": "application/json"}) == 400
        assert post(session, b"plain", {"Content-Type": "text/plain"}) == 415
    finally:
        session.close()
    assert (tmp_path / "raw/000001.json").read_bytes() == b"{not json"
    assert (tmp_path / "raw/000002.bin").read_bytes() == b"plain"
    rejected = [e for e in index(tmp_path) if e["event"] == "rejected"]
    assert [e["reason"] for e in rejected] == ["Invalid OTLP trace export", "Unsupported OTLP content type"]
    status = json.loads((tmp_path / "status.json").read_text())
    # An unsupported content type is archived but, as before, is not a collection error.
    assert status["rejected_batches"] == 1 and status["raw_batches"] == 2


def test_file_export_archives_the_agents_own_file(tmp_path):
    cfg = parse_config({"otel": {"profile": "file-export", "file": "trace.json", "file_format": "otlp-json"}})
    session = create_session(cfg, tmp_path, "example")
    body = json.dumps(BATCH, indent=2).encode()
    Path(session.environment["ABB_OTEL_FILE"]).write_bytes(body)
    session.close()
    assert (tmp_path / "raw/000001-trace.json").read_bytes() == body
    assert json.loads((tmp_path / "spans.jsonl").read_text())["archive"] == {
        "file": "otel/raw/000001-trace.json", "batch": 1}


def test_published_archive_stays_owner_only(tmp_path):
    session = create_session(CaptureConfig("native-otlp"), tmp_path / "spool", "example")
    try:
        assert post(session, json.dumps(BATCH).encode(), {"Content-Type": "application/json"}) == 200
    finally:
        session.close()
    publish_capture(tmp_path / "spool", tmp_path / "otel")
    assert (tmp_path / "otel/raw/000001.json").read_bytes() == json.dumps(BATCH).encode()
    assert_owner_only(tmp_path / "otel")


def test_artifact_readers_refuse_the_raw_archive(tmp_path):
    from agentbench.observe.artifact_paths import artifact_file, is_raw_trace
    (tmp_path / "otel/raw").mkdir(parents=True)
    (tmp_path / "otel/raw/000001.pb").write_bytes(b"raw")
    (tmp_path / "otel/spans.jsonl").write_text("{}\n")
    assert is_raw_trace("otel/raw/000001.pb") and is_raw_trace("invocation-x/output/otel/raw/index.jsonl")
    assert not is_raw_trace("otel/spans.jsonl") and not is_raw_trace("raw/otel")
    assert artifact_file(tmp_path, "otel/spans.jsonl").is_file()
    with pytest.raises(ValueError, match="not served"):
        artifact_file(tmp_path, "otel/raw/000001.pb")


def test_judge_request_never_attaches_the_raw_archive(tmp_path):
    from agentbench.sdk.judges import build_request
    step = tmp_path / "steps/0001"
    (step / "output/otel/raw").mkdir(parents=True)
    (step / "input.json").write_text(json.dumps({"input_id": "a"}))
    (step / "result.json").write_text(json.dumps({"status": "ok"}))
    (step / "output/otel/raw/000001.pb").write_bytes(b"raw")
    (step / "output/otel/spans.jsonl").write_text("{}\n")
    (tmp_path / "manifest.json").write_text(json.dumps({
        "run_id": "run", "evidence": "complete", "steps": [{"directory": "steps/0001"}]}))
    case = {"case_id": "c", "inputs": [{"input_id": "a", "payload": "hi"}]}
    request = build_request(tmp_path, SimpleNamespace(agent_id="example"), {"case": case})
    assert "steps/0001/output/otel/spans.jsonl" in request["attachments"]
    assert not any("otel/raw" in name for name in request["attachments"])


def test_run_summary_skips_the_raw_index(tmp_path):
    from agentbench.observe.store import summarize
    session = create_session(CaptureConfig("native-otlp"), tmp_path / "otel", "example")
    try:
        assert post(session, json.dumps(BATCH).encode(), {"Content-Type": "application/json"}) == 200
    finally:
        session.close()
    # The raw index is JSONL with its own shape; the run summary must not read it as events.
    assert summarize(tmp_path) == {"agent_otel:span": 1}
