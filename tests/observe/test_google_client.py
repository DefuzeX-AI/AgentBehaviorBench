"""Callback regression with stubbed RPCs; network evidence is in acceptance/interception."""
import asyncio
import pytest

@pytest.mark.parametrize("streaming", [False, True])
def test_original_google_ainvoke_and_astream(monkeypatch, tmp_path, streaming):
    genai = pytest.importorskip("langchain_google_genai")
    from google.ai.generativelanguage_v1beta import GenerativeServiceAsyncClient, GenerateContentResponse
    from agentbench.observe.langchain import TraceCallback
    from agentbench.observe.store import TraceStore
    seen = []

    async def generate(self, request=None, **kwargs):
        seen.append(type(self.transport).__name__)
        assert "GrpcAsyncIO" in type(self.transport).__name__
        return GenerateContentResponse(candidates=[{"content": {"role": "model", "parts": [{"text": "中文响应"}]}, "finish_reason": "STOP"}])

    async def stream(self, request=None, **kwargs):
        response = await generate(self, request, **kwargs)
        async def chunks():
            yield response
        return chunks()

    monkeypatch.setattr(GenerativeServiceAsyncClient, "generate_content", generate)
    monkeypatch.setattr(GenerativeServiceAsyncClient, "stream_generate_content", stream)
    llm = genai.ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key="temporary", max_retries=0)
    assert "GrpcTransport" in type(llm.client.transport).__name__
    store = TraceStore(tmp_path / "trace.jsonl", "test", source="framework")

    async def run():
        try:
            config = {"callbacks": [TraceCallback(store)]}
            if streaming:
                return "".join([chunk.content async for chunk in llm.astream("你好", config=config)])
            return (await llm.ainvoke("你好", config=config)).content
        finally:
            if llm.async_client_running is not None:
                await llm.async_client_running.transport.close()
    try:
        assert asyncio.run(run()) == "中文响应"
    finally:
        llm.client.transport.close()
    assert seen
