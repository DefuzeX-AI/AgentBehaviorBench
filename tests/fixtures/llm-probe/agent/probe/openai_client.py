"""Original OpenAI SDK: sync/async Chat Completions and Responses."""
import asyncio
from .registry import register

def install(api, asynchronous, streaming):
    name = f"openai.{api}.{'async' if asynchronous else 'sync'}.{'stream' if streaming else 'unary'}"
    @register(name, streaming=streaming)
    async def run(settings, receive):
        from openai import OpenAI, AsyncOpenAI
        args = dict(model=settings["models"]["openai"], stream=streaming)
        if api == "chat":
            args.update(messages=[{"role": "user", "content": settings["prompt"]}], max_tokens=48)
        else:
            args.update(input=settings["prompt"], max_output_tokens=48)
        def text(value):
            if api == "chat":
                return ((value.choices[0].delta.content if streaming else value.choices[0].message.content) or "") if value.choices else ""
            return getattr(value, "delta", "") if streaming and getattr(value, "type", "") == "response.output_text.delta" else ("" if streaming else value.output_text)
        def sync():
            with OpenAI(timeout=25, max_retries=0) as client:
                response = (client.chat.completions if api == "chat" else client.responses).create(**args)
                if streaming:
                    with response:
                        for chunk in response:
                            receive(text(chunk))
                else:
                    receive(text(response))
        if not asynchronous:
            await asyncio.to_thread(sync)
            return
        async with AsyncOpenAI(timeout=25, max_retries=0) as client:
            response = await (client.chat.completions if api == "chat" else client.responses).create(**args)
            if streaming:
                async with response:
                    async for chunk in response:
                        receive(text(chunk))
            else:
                receive(text(response))

for api in ("chat", "responses"):
    for asynchronous in (False, True):
        for streaming in (False, True):
            install(api, asynchronous, streaming)
