"""Ollama original local HTTP API; no server/base URL rewrite."""
import asyncio
from .registry import register

def install(api, asynchronous, streaming):
    @register(f"ollama.{api}.{'async' if asynchronous else 'sync'}.{'stream' if streaming else 'unary'}", streaming=streaming)
    async def run(settings, receive):
        from ollama import Client, AsyncClient
        args = dict(model=settings["models"]["ollama"], stream=streaming, options={"num_predict": 48})
        args.update({"prompt": settings["prompt"]} if api == "generate" else {"messages": [{"role": "user", "content": settings["prompt"]}]})
        def text(value):
            return value.response if api == "generate" else value.message.content
        if asynchronous:
            client = AsyncClient(timeout=25)
            try:
                value = await getattr(client, api)(**args)
                if streaming:
                    async for item in value:
                        receive(text(item))
                else:
                    receive(text(value))
            finally:
                await client._client.aclose()
        else:
            def sync():
                client = Client(timeout=25)
                try:
                    value = getattr(client, api)(**args)
                    if streaming:
                        for item in value:
                            receive(text(item))
                    else:
                        receive(text(value))
                finally:
                    client._client.close()
            await asyncio.to_thread(sync)

for api in ("chat", "generate"):
    for asynchronous in (False, True):
        for streaming in (False, True):
            install(api, asynchronous, streaming)

