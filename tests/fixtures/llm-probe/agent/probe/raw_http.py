"""OpenAI-compatible providers used by the inventory, without an SDK."""
import asyncio
import json
import os
from .registry import register

def install(provider, url, streaming):
    @register(f"http.{provider}.{'stream' if streaming else 'unary'}", streaming=streaming)
    async def run(settings, receive):
        import httpx
        async with httpx.AsyncClient(timeout=25) as client:
            async with client.stream("POST", url, headers={"authorization": "Bearer " + os.environ["OPENAI_API_KEY"]},
                    json={"model": settings["models"][provider], "messages": [{"role": "user", "content": settings["prompt"]}],
                          "stream": streaming, "max_tokens": 48}) as response:
                response.raise_for_status()
                if streaming:
                    buffer = b""
                    async for part in response.aiter_bytes():
                        buffer += part
                        buffer = buffer.replace(b"\r\n", b"\n")
                        while b"\n\n" in buffer:
                            frame, _, buffer = buffer.partition(b"\n\n")
                            data = b"\n".join(line[5:].lstrip() for line in frame.split(b"\n") if line.startswith(b"data:"))
                            if not data or data == b"[DONE]":
                                continue
                            event = json.loads(data)
                            for choice in event.get("choices", []):
                                receive(choice.get("delta", {}).get("content", ""))
                else:
                    receive(json.loads(await response.aread())["choices"][0]["message"]["content"])

for provider, url in (("deepseek", "https://api.deepseek.com/chat/completions"),
                      ("qwen", "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions")):
    for streaming in (False, True):
        install(provider, url, streaming)
