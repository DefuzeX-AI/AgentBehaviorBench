"""Offline protocol contract tests; real client/network acceptance is opt-in."""
import gzip
import json
from pathlib import Path
import struct
import sys
from types import SimpleNamespace
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "agentbench/services/model-interceptor/src"))
from model.google.gemini import GeminiWire
from defuzex_model_interceptor.registry import load_wires
from defuzex_model_interceptor.transport.json import json_bytes
from defuzex_model_interceptor.transport.sse import SSEDecoder
from model.ollama import OllamaWire
from defuzex_model_interceptor.routing.policy import EgressPolicy
from defuzex_model_interceptor.config import ToolRoute, Route

def source(data, path="/v1beta/models/gemini:generateContent", headers=None):
    return SimpleNamespace(content=json_bytes(data), path=path, headers=headers or {})

def chat(text="中文\u2028\u2029"):
    return {"choices": [{"index": 0, "delta": {"content": text}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}}

@pytest.mark.parametrize("size", [1, 2, 3, 7, 64, 4096])
def test_sse_arbitrary_fragments_unicode_multiline_and_terminal(size):
    encoded = b": comment\r\n\r\ndata: " + json_bytes(chat()) + b"\r\n\r\ndata: [DONE]\r\n\r\n"
    parser = SSEDecoder()
    result = []
    for i in range(0, len(encoded), size):
        result.extend(parser.feed(encoded[i:i+size]))
    result.extend(parser.feed(b""))
    assert result == [chat()]
    assert parser.done

@pytest.mark.parametrize("data", [
    b'data: {"choices":[]}\n\n', b'data: {"error":{"message":"failed"}}\n\n',
    b'data: [DONE]\n\ndata: {}\n\n', b'data: {"type":"response.failed"}\n\n',
    b'data: [DO', b'data: []\n\n',
])
def test_sse_malformed_error_and_missing_terminal_fail(data):
    parser = SSEDecoder()
    with pytest.raises(ValueError):
        parser.feed(data)
        parser.feed(b"")

@pytest.mark.parametrize("terminal", ["message_stop", "response.completed"])
def test_native_terminal_events(terminal):
    parser = SSEDecoder(terminal)
    parser.feed(b"data: " + json_bytes({"type": terminal}) + b"\n\ndata: [DONE]\n\n")
    parser.feed(b"")
    assert parser.done

def test_multiline_sse_data():
    assert SSEDecoder().feed(b'data: {"choices":\ndata: []}\n\n') == [{"choices": []}]

def test_sse_event_size_is_bounded():
    with pytest.raises(ValueError):
        SSEDecoder(maximum=5).feed(b"data: longer")

@pytest.mark.parametrize("compression", [False, True])
def test_grpc_protobuf_unary_and_stream_roundtrip(compression):
    pytest.importorskip("google.ai.generativelanguage_v1beta")
    from google.ai.generativelanguage_v1beta import GenerateContentRequest, GenerateContentResponse
    from model.google.grpc import unpack_request, pack_response
    request = GenerateContentRequest(model="models/gemini", contents=[{"role": "user", "parts": [{"text": "你好"}]}])
    body = GenerateContentRequest.serialize(request)
    if compression:
        body = gzip.compress(body)
    raw = struct.pack(">BI", int(compression), len(body)) + body
    decoded = unpack_request(raw, "gzip" if compression else "identity")
    assert decoded["contents"][0]["parts"][0]["text"] == "你好"
    wire = GeminiWire(grpc=True)
    wire.decode(SimpleNamespace(content=raw, headers={"content-type": "application/grpc", "grpc-encoding": "gzip"},
              path="/google.ai.generativelanguage.v1beta.GenerativeService/StreamGenerateContent"))
    codec = wire.stream()
    out = b"".join(codec.feed(bytes([b])) for b in b"data: " + json_bytes(chat()) + b"\n\ndata: [DONE]\n\n") + codec.feed(b"")
    assert out[:1] == b"\x00"
    message = GenerateContentResponse.deserialize(out[5:])
    assert message.candidates[0].content.parts[0].text == chat()["choices"][0]["delta"]["content"]
    assert message.usage_metadata.total_token_count == 3

@pytest.mark.parametrize("raw,encoding", [(b"", "identity"), (b"\x02\x00\x00\x00\x00", "identity"),
    (b"\x01\x00\x00\x00\x00", "snappy"), (b"\x00\x00\x00\x00\x00extra", "identity")])
def test_grpc_bad_frames_fail(raw, encoding):
    pytest.importorskip("google.ai.generativelanguage_v1beta")
    from model.google.grpc import unpack_request
    with pytest.raises(ValueError):
        unpack_request(raw, encoding)

def test_grpc_unknown_proto_fields_are_not_dropped():
    pytest.importorskip("google.ai.generativelanguage_v1beta")
    from model.google.grpc import unpack_request
    # Unknown field 1000, varint 1.
    body = b"\xc0\x3e\x01"
    with pytest.raises(ValueError, match="Unknown"):
        unpack_request(struct.pack(">BI", 0, len(body)) + body)

@pytest.mark.parametrize("field,value", [("tools", [{"functionDeclarations": []}]), ("cachedContent", "x"),
    ("generationConfig", {"topK": 2}), ("contents", [{"parts": [{"inlineData": {"mimeType": "image/png", "data": "AA=="}}]}])])
def test_gemini_unsupported_semantics_rejected(field, value):
    payload = {"contents": [{"parts": [{"text": "hello"}]}], field: value}
    with pytest.raises(ValueError):
        GeminiWire().decode(source(payload))

@pytest.mark.parametrize("generate", [False, True])
def test_ollama_text_stream_and_usage(generate):
    wire = OllamaWire(generate)
    payload = {"model": "qwen", "prompt": "你好"} if generate else {"model": "qwen", "messages": [{"role": "user", "content": "你好"}]}
    _, converted = wire.decode(source(payload))
    assert converted["stream"] is True
    stream = wire.stream()
    first = stream.feed(b"data: " + json_bytes(chat()) + b"\n\n")
    assert first and not json.loads(first)["done"]
    tail = stream.feed(b"data: [DONE]\n\n") + stream.feed(b"")
    final = json.loads(tail)
    assert final["done"] and final["eval_count"] == 2

@pytest.mark.parametrize("extra", [{"tools": [{}]}, {"format": "json"}, {"options": {"num_ctx": 1024}},
                                    {"messages": [{"role": "user", "content": "x", "images": ["AA"]}]}])
def test_ollama_rejects_unsupported_fields(extra):
    with pytest.raises(ValueError):
        OllamaWire().decode(source({"model": "qwen", "messages": [{"role": "user", "content": "x"}], **extra}))

def test_wires_are_per_call_instances():
    factories = load_wires()
    assert factories["gemini-grpc"]() is not factories["gemini-grpc"]()
    assert factories["openai-responses"]().endpoint == "/responses"

def test_tool_allowlist_cannot_bypass_model_host():
    policy = EgressPolicy(SimpleNamespace(routes=(Route("model", ("api.example.com",), (443,), ("POST",), ("/v1/chat",), "openai-chat", "key"),),
        tool_routes=(ToolRoute(("api.example.com", "search.example.com"), (443,), ("POST",), ("/search",)),)))
    def req(host, path):
        return SimpleNamespace(pretty_host=host, port=443, method="POST", path=path)
    assert policy.permits_tool(req("search.example.com", "/search"))
    assert not policy.permits_tool(req("api.example.com", "/search"))
    assert not policy.permits_tool(req("unknown.example.com", "/search"))
    assert not policy.permits_tool(req("search.example.com", "/redirect"))

