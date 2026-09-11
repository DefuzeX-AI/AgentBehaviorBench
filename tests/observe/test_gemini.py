import json
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/model-interceptor/src"))
from defuzex_model_interceptor.gemini import GeminiStream, request_to_chat, response_from_chat


def test_request_mapping_and_rejection():
    mapped = request_to_chat({"contents": [{"role": "user", "parts": [{"text": "你好"}]}],
                              "generationConfig": {"temperature": 0, "maxOutputTokens": 10}}, streaming=False)
    assert mapped["messages"] == [{"role": "user", "content": "你好"}]
    assert mapped["max_tokens"] == 10
    with pytest.raises(ValueError):
        request_to_chat({"contents": [], "tools": [{"googleSearch": {}}]}, streaming=False)
    with pytest.raises(ValueError):
        request_to_chat({"contents": [{"parts": [{"inlineData": {}}]}]}, streaming=False)


@pytest.mark.parametrize("size", [1, 2, 3, 11, 10000])
@pytest.mark.parametrize("sse", [True, False])
def test_fragmented_stream_roundtrip(size, sse):
    content = b""
    for text in ("你", "好\n\"world\""):
        content += ("data: " + json.dumps({"choices": [{"index": 0, "delta": {"content": text}}]}, ensure_ascii=False) + "\r\n\r\n").encode()
    content += b'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":2,"completion_tokens":3,"total_tokens":5}}\n\ndata: [DONE]\n\n'
    parser = GeminiStream(sse=sse)
    result = b"".join(parser.feed(content[i:i + size]) for i in range(0, len(content), size)) + parser.feed(b"")
    rows = [json.loads(line[6:]) for line in result.splitlines() if line.startswith(b"data: ")] if sse else json.loads(result)
    assert "".join(r["candidates"][0]["content"]["parts"][0]["text"] for r in rows) == '你好\n"world"'
    assert rows[-1]["candidates"][0]["finishReason"] == "STOP"
    assert rows[-1]["usageMetadata"]["totalTokenCount"] == 5


def test_incomplete_stream_rejected():
    with pytest.raises(ValueError, match="Incomplete"):
        GeminiStream().feed(b"")


def test_original_google_response_parser():
    module = pytest.importorskip("google.ai.generativelanguage_v1beta.types.generative_service")
    translated = response_from_chat({"choices": [{"message": {"content": "原客户端"}, "finish_reason": "stop"}]})
    parsed = module.GenerateContentResponse.from_json(json.dumps(translated))
    assert parsed.candidates[0].content.parts[0].text == "原客户端"
