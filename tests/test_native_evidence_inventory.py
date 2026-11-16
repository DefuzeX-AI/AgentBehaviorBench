import json
import pytest
from agentbench.observe.evidence_inventory import validate_native_references, payload_paths, recover_payloads


def source(root, ref="otel-payloads/input.json"):
    out = root / "invocation-a/output"
    out.mkdir(parents=True)
    row = {"schema":"abb.observe.event.v1", "source":"otel", "event":"span", "run_id":"run",
           "data":{"span_id":"span", "attributes":{"abb.input_ref":ref}}}
    (out / "otel.jsonl").write_text(json.dumps(row)+"\n", encoding="utf-8")
    return out


def test_missing_payload_and_recovery(tmp_path):
    original, snapshot = tmp_path / "original", tmp_path / "snapshot"
    out = source(original); source(snapshot)
    (out / "otel-payloads").mkdir()
    raw = '"你好 España"'.encode()
    (out / "otel-payloads/input.json").write_bytes(raw)
    with pytest.raises(ValueError, match="Missing native evidence"):
        validate_native_references(snapshot)
    restored = recover_payloads(original, snapshot)
    assert len(restored) == 1
    assert (snapshot / restored[0]["path"]).read_bytes() == raw
    assert validate_native_references(snapshot)["references_verified"] == 1
    assert len(payload_paths(snapshot)) == 1


@pytest.mark.parametrize("ref", ["../../secret", "/etc/passwd", "C:/secret", "otel-payloads/../secret"])
def test_unsafe_reference(tmp_path, ref):
    source(tmp_path, ref)
    with pytest.raises(ValueError):
        validate_native_references(tmp_path)


def test_recovery_rejects_other_execution(tmp_path):
    original, snapshot = tmp_path / "a", tmp_path / "b"
    out = source(original); source(snapshot)
    p = out / "otel.jsonl"
    p.write_text(p.read_text().replace('"span_id": "span"', '"span_id": "other"'))
    with pytest.raises(ValueError, match="differs"):
        recover_payloads(original, snapshot)


def test_symlink_rejected(tmp_path):
    out=source(tmp_path)
    (out / "otel-payloads").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        validate_native_references(tmp_path)


def test_complete_snapshot_does_not_depend_on_old_worker(tmp_path):
    original, snapshot = tmp_path / "gone", tmp_path / "snapshot"
    out = source(snapshot)
    (out / "otel-payloads").mkdir()
    (out / "otel-payloads/input.json").write_bytes(b'"actual"')
    assert recover_payloads(original, snapshot) == []


def test_live_partial_otel_line_is_deferred(tmp_path):
    out = source(tmp_path)
    p = out / "otel.jsonl"
    p.write_bytes(p.read_bytes() + b'{"source":')
    assert payload_paths(tmp_path, allow_incomplete=True)
    with pytest.raises(ValueError):
        payload_paths(tmp_path)
