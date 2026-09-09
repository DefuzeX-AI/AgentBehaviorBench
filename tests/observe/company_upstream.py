"""OFFLINE TEST ONLY: controlled HTTP responses for the unchanged Company graph.

Never imported by production execution. Original SDK serializers, LangChain
clients, Tavily methods, graph nodes and graph edges still execute.
"""
import json


def install():
    import httpx
    import requests

    class Body(httpx.AsyncByteStream):
        def __init__(self, data):
            self.data = data

        async def __aiter__(self):
            for index in range(0, len(self.data), 17):
                yield self.data[index:index + 17]

    async def httpx_send(self, request, *args, **kwargs):
        if request.url.host == "api.openai.com":
            payload = json.loads(request.content)
            text = "Example company revenue\n" if payload["model"] == "gpt-5.1" else "OFFLINE REPORT: verified execution, not real research."
            if payload.get("stream"):
                rows = [{"id": "chatcmpl-offline", "object": "chat.completion.chunk", "created": 1,
                         "model": payload["model"], "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}]},
                        {"id": "chatcmpl-offline", "object": "chat.completion.chunk", "created": 1,
                         "model": payload["model"], "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}]
                data = ("".join("data: " + json.dumps(r) + "\n\n" for r in rows) + "data: [DONE]\n\n").encode()
                return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=Body(data), request=request)
            return httpx.Response(200, json={"id": "offline", "choices": [{"index": 0,
                "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}]}, request=request)
        if request.url.host == "api.tavily.com":
            return httpx.Response(200, json={"results": [{"url": "https://example.test/report", "title": "Offline evidence",
                 "content": "Controlled research evidence.", "raw_content": "Controlled research evidence.", "score": 0.95}],
                 "failed_results": [], "response_time": 0.1}, request=request)
        raise AssertionError(f"Offline test attempted unexpected HTTP: {request.url.host}")

    def requests_send(self, request, *args, **kwargs):
        if not request.url.startswith("https://generativelanguage.googleapis.com/"):
            raise AssertionError("Offline test attempted unexpected requests HTTP")
        from defuzex_model_interceptor.gemini import request_to_chat, response_from_chat
        request_to_chat(json.loads(request.body), streaming=False)
        response = requests.Response()
        response.status_code = 200
        response.headers["content-type"] = "application/json"
        response.encoding = "utf-8"
        response._content = json.dumps(response_from_chat({"choices": [{"message": {"content": "Offline evidence briefing."}, "finish_reason": "stop"}]})).encode()
        return response

    httpx.AsyncClient.send = httpx_send
    requests.Session.send = requests_send
