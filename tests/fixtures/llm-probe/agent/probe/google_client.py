"""Google original transports; no monkey patch or forced REST."""
import asyncio
import os
from .registry import register

def install(transport, asynchronous, streaming):
    name = f"google.{transport}.{'async' if asynchronous else 'sync'}.{'stream' if streaming else 'unary'}"
    @register(name, streaming=streaming)
    async def run(settings, receive):
        from google.ai.generativelanguage_v1beta import GenerativeServiceClient, GenerativeServiceAsyncClient
        args = dict(request={"model": "models/" + settings["models"]["google"],
                    "contents": [{"role": "user", "parts": [{"text": settings["prompt"]}]}],
                    "generation_config": {"max_output_tokens": 48}}, retry=None, timeout=25)
        options = {"api_key": os.environ["GEMINI_API_KEY"]}
        def text(value):
            return "".join(p.text for c in value.candidates for p in c.content.parts)
        if asynchronous:
            client = GenerativeServiceAsyncClient(client_options=options)
            try:
                method = client.stream_generate_content if streaming else client.generate_content
                value = await method(**args)
                if streaming:
                    async for item in value:
                        receive(text(item))
                else:
                    receive(text(value))
            finally:
                await client.transport.close()
        else:
            def sync():
                with GenerativeServiceClient(client_options=options, transport=transport) as client:
                    value = (client.stream_generate_content if streaming else client.generate_content)(**args)
                    if streaming:
                        for item in value:
                            receive(text(item))
                    else:
                        receive(text(value))
            await asyncio.to_thread(sync)

for transport in ("grpc", "rest"):
    for asynchronous in ((False, True) if transport == "grpc" else (False,)):
        for streaming in (False, True):
            install(transport, asynchronous, streaming)

def install_langchain(streaming):
    @register(f"langchain.google.async.{'stream' if streaming else 'unary'}", streaming=streaming)
    async def run(settings, receive):
        from langchain_google_genai import ChatGoogleGenerativeAI
        llm = ChatGoogleGenerativeAI(model=settings["models"]["google"],
                google_api_key=os.environ["GEMINI_API_KEY"], max_output_tokens=48, max_retries=0, timeout=25)
        try:
            if streaming:
                async for item in llm.astream(settings["prompt"]):
                    receive(item.content)
            else:
                receive((await llm.ainvoke(settings["prompt"])).content)
        finally:
            llm.client.transport.close()
            client = llm.async_client_running
            if client is not None:
                await client.transport.close()

for streaming in (False, True):
    install_langchain(streaming)

