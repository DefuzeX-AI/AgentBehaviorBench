"""Run the upstream QNN pipeline with text input and live ABB callbacks.

The deployment selects native QNN parameters via adapter.context. Each input is
an independent brief; no conversation history, tools or synthetic graph is added.
"""
from __future__ import annotations

import asyncio
from collections.abc import Mapping

_ALLOWED_CONTEXT_KEYS = frozenset({
    'qnn_mode', 'manual_layers', 'manual_width', 'num_epochs',
    'vector_word_size', 'learning_rate', 'attention_top_k', 'enable_self_attention',
})


def prompt_from_input(value):
    if isinstance(value, Mapping):
        if set(value) != {'user_prompt'}:
            raise ValueError("Expected exactly one 'user_prompt' field")
        value = value['user_prompt']
    if not isinstance(value, str) or not value.strip():
        raise ValueError('user_prompt must be a non-empty string')
    return value


def params_from_context(context):
    if context is None:
        return {}
    if not isinstance(context, Mapping) or set(context) - _ALLOWED_CONTEXT_KEYS:
        raise ValueError('Unsupported QNN deployment parameters')
    return dict(context)


class OpenDeepThink:
    def __init__(self):
        self._closed = False

    async def ainvoke(self, value, config=None, *, context=None):
        if self._closed:
            raise RuntimeError('open-deepthink binding is closed')
        prompt = prompt_from_input(value)
        params = params_from_context(context)
        from deepthink.api import run_qnn
        from deepthink.providers import create_llm
        from langchain_core.runnables.config import set_config_context
        from openai import DefaultHttpxClient, DefaultAsyncHttpxClient

        # Use OpenAI's own timeout/connection defaults. Clients belong to this
        # invocation, so repeated sync calls cannot reuse a closed event loop.
        with DefaultHttpxClient() as http_client:
            async with DefaultAsyncHttpxClient() as http_async_client:
                llm = create_llm(provider='openrouter', http_client=http_client,
                                 http_async_client=http_async_client)
                # run_qnn has no config argument. LangChain's runnable context
                # carries the worker's live callbacks through every native chain.
                # Creating the task inside the copied context also works on 3.10.
                with set_config_context(config or {}) as ctx:
                    task = ctx.run(asyncio.create_task,
                                   run_qnn(llm, prompt, params=params or None))
                    return await task

    def invoke(self, value, config=None, *, context=None):
        return asyncio.run(self.ainvoke(value, config, context=context))

    def close(self):
        self._closed = True

    async def aclose(self):
        self.close()


def create_graph():
    return OpenDeepThink()
