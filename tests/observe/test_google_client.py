"""Run the pinned LangChain/Google client against a controlled HTTP transport."""
import asyncio
import json
from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/model-interceptor/src"))
from defuzex_model_interceptor.gemini import GeminiStream, request_to_chat, response_from_chat


@pytest.mark.parametrize("streaming", [False, True])
def test_original_google_ainvoke_and_astream(monkeypatch, tmp_path, streaming):
    genai = pytest.importorskip("langchain_google_genai")
    import requests
    from agentbench.observe.google_rest import use_google_rest
    from agentbench.observe.langchain import TraceCallback
    from agentbench.observe.store import TraceStore
    from agentbench.observe.correlation import model_correlation

    seen = []

    def send(self, request, **kwargs):
        assert request.headers["x-goog-api-key"] == "temporary"
        assert request.headers.get("x-abb-framework-span")
        body = request_to_chat(json.loads(request.body), streaming=streaming)
        seen.append(body)
        response = requests.Response()
        response.status_code = 200
        response.headers["content-type"] = "application/json; charset=utf-8"
        response.encoding = "utf-8"
        payload = {"choices": [{"index": 0, "message": {"content": "中文响应"}, "finish_reason": "stop"}],
                   "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5}}
        if streaming:
            source = ("data: " + json.dumps(payload, ensure_ascii=False) + "\n\ndata: [DONE]\n\n").encode()
            codec = GeminiStream()
            data = b"".join(codec.feed(bytes([byte])) for byte in source) + codec.feed(b"")
        else:
            data = json.dumps(response_from_chat(payload), ensure_ascii=False).encode()
        response._content = data
        response._content_consumed = True
        return response

    monkeypatch.setattr(requests.Session, "send", send)
    llm = genai.ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key="temporary", temperature=0, max_retries=0)
    use_google_rest(llm)
    store = TraceStore(tmp_path / "trace.jsonl", "test", source="framework")

    async def run():
        config = {"callbacks": [TraceCallback(store)]}
        with model_correlation(["generativelanguage.googleapis.com"]):
            if streaming:
                chunks = [chunk async for chunk in llm.astream("你好", config=config)]
                return "".join(chunk.content for chunk in chunks)
            return (await llm.ainvoke("你好", config=config)).content
    try:
        assert asyncio.run(run()) == "中文响应"
    finally:
        llm.client.transport.close()
    assert seen[0]["messages"][0]["content"] == "你好"
