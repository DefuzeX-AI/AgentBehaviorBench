"""Async scheduling over Google's original synchronous REST client.

langchain-google-genai 3.0.3 otherwise switches ainvoke back to grpc_asyncio,
even with transport='rest'. This bridge changes transport, not model semantics.
"""
import asyncio


class AsyncRestClient:
    def __init__(self, client):
        self.client = client

    async def generate_content(self, **kwargs):
        return await asyncio.to_thread(self.client.generate_content, **kwargs)

    async def stream_generate_content(self, **kwargs):
        iterator = await asyncio.to_thread(self.client.stream_generate_content, **kwargs)
        sentinel = object()

        async def stream():
            try:
                while True:
                    item = await asyncio.to_thread(next, iterator, sentinel)
                    if item is sentinel:
                        break
                    yield item
            finally:
                cancel = getattr(iterator, "cancel", None)
                if callable(cancel):
                    cancel()
        return stream()


def use_google_rest(llm):
    from langchain_google_genai._genai_extension import build_generative_service
    old = llm.client
    key = llm.google_api_key
    key = key.get_secret_value() if hasattr(key, "get_secret_value") else key
    llm.client = build_generative_service(credentials=llm.credentials, api_key=key,
                                          client_options=llm.client_options, transport="rest")
    llm.transport = "rest"
    llm.async_client_running = AsyncRestClient(llm.client)
    old.transport.close()
