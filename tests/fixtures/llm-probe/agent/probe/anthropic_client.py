"""Anthropic original Messages API."""
import asyncio
from .registry import register

def install(asynchronous, streaming):
    @register(f"anthropic.{'async' if asynchronous else 'sync'}.{'stream' if streaming else 'unary'}", streaming=streaming)
    async def run(settings, receive):
        from anthropic import Anthropic, AsyncAnthropic
        args = dict(model=settings["models"]["anthropic"], max_tokens=48, stream=streaming,
                    messages=[{"role": "user", "content": settings["prompt"]}])
        def text(value):
            if streaming:
                return getattr(getattr(value, "delta", None), "text", "")
            return "".join(getattr(p, "text", "") for p in value.content)
        if asynchronous:
            async with AsyncAnthropic(timeout=25, max_retries=0) as client:
                value = await client.messages.create(**args)
                if streaming:
                    async with value:
                        async for item in value:
                            receive(text(item))
                else:
                    receive(text(value))
        else:
            def sync():
                with Anthropic(timeout=25, max_retries=0) as client:
                    value = client.messages.create(**args)
                    if streaming:
                        with value:
                            for item in value:
                                receive(text(item))
                    else:
                        receive(text(value))
            await asyncio.to_thread(sync)

for asynchronous in (False, True):
    for streaming in (False, True):
        install(asynchronous, streaming)

