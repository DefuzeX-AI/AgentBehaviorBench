import gzip
import zlib
import brotli
import pytest
from defuzex_model_interceptor.observation.body import prepare_body


@pytest.mark.parametrize("encoding,compress", [("identity", lambda b:b), ("gzip", gzip.compress), ("deflate", zlib.compress), ("br", brotli.compress)])
def test_decode_then_redact_without_changing_wire(encoding, compress):
    plain = "你好 España secret".encode()
    wire = compress(plain)
    result = prepare_body(wire, encoding=encoding, limit=10000, complete=True,
                          redact=lambda b:b.replace(b"secret", b"******"))
    assert result.body == plain.replace(b"secret", b"******")
    assert result.complete
    assert result.metadata["body_representation"] == "decoded_redacted"
    assert wire == compress(plain)


@pytest.mark.parametrize("encoding,compress", [("gzip", gzip.compress), ("deflate", zlib.compress), ("br", brotli.compress)])
def test_bounded_decode(encoding, compress):
    result = prepare_body(compress(b"x" * 1000000), encoding=encoding, limit=100,
                          complete=True, redact=lambda b:b)
    assert not result.complete
    assert result.metadata["body_gap"] == "decoded_body_limit_exceeded"
    assert result.body == b""


def test_corrupt_unknown_and_interrupted():
    for encoding, body in [("gzip", b"broken"), ("unknown", b"secret"), ("gzip", gzip.compress(b"secret")[:-4])]:
        result = prepare_body(body, encoding=encoding, limit=100, complete=True, redact=lambda b:b)
        assert result.body == b""
        assert not result.complete and result.metadata["body_gap"]
    result = prepare_body(b"partial", encoding="identity", limit=100, complete=False, redact=lambda b:b)
    assert result.body == b"partial" and not result.complete


@pytest.mark.parametrize("encoding,compress", [("identity", lambda b:b), ("gzip", gzip.compress), ("deflate", zlib.compress), ("br", brotli.compress)])
def test_observer_stream_forwarding_and_saved_evidence(tmp_path, encoding, compress):
    import json
    from types import SimpleNamespace
    from defuzex_model_interceptor.observation.http_observer import HTTPObserver
    plain = "你好 secret España".encode()
    wire = compress(plain)
    flow = SimpleNamespace(id="request", metadata={}, request=SimpleNamespace(
        headers={}, pretty_url="https://example.test/data", method="GET", content=b""),
        response=SimpleNamespace(headers={"content-encoding":encoding}, status_code=200, stream=None))
    observer = HTTPObserver(tmp_path, limit=10000, secrets=["secret"])
    observer.request(flow)
    observer.responseheaders(flow)
    forwarded = b"".join(flow.response.stream(wire[i:i+3]) for i in range(0,len(wire),3))
    observer.response(flow)
    assert forwarded == wire
    assert (tmp_path / "request.response").read_bytes() == plain.replace(b"secret", b"******")
    meta = json.loads((tmp_path / "request.json").read_text())
    assert meta["complete"] and meta["received_bytes"] == len(wire)
    assert meta["body_representation"] == "decoded_redacted"
