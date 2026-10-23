"""Run Mini-Agent's own ACP server (mini_agent.acp) with two launcher-side compatibility shims.

Agent code, tools and the ACP turn loop are not modified:

1. ``run_acp_server`` constructs ``LLMClient`` without ``provider``, so the ACP path
   always speaks the Anthropic protocol and ignores ``provider`` in config.yaml. The CLI
   path passes the configured provider (``cli.py``: ``"anthropic"`` -> Anthropic, anything
   else -> OpenAI); the same mapping is applied to the ACP server's ``LLMClient``.
2. Tool loading at startup and per session ``print``s status lines to stdout, which is
   the JSON-RPC channel. Python-level stdout is redirected to stderr, and only the ACP
   stream writer created by ``stdio_streams`` is bound to the original stdout pipe.
"""
from __future__ import annotations

import functools
import os
import sys


def bind_streams(acp_module, channel) -> None:
    upstream = acp_module.stdio_streams

    async def stdio_streams():
        saved, sys.stdout = sys.stdout, channel
        try:
            return await upstream()
        finally:
            sys.stdout = saved

    acp_module.stdio_streams = stdio_streams


def bind_provider(acp_module, configured: str) -> None:
    from mini_agent.llm import LLMClient
    from mini_agent.schema import LLMProvider

    provider = LLMProvider.ANTHROPIC if configured.lower() == "anthropic" else LLMProvider.OPENAI
    acp_module.LLMClient = functools.partial(LLMClient, provider=provider)


def main() -> None:
    sys.stdout.flush()
    channel = os.fdopen(os.dup(1), "wb", buffering=0)
    os.dup2(2, 1)

    import mini_agent.acp as acp_module
    from mini_agent.config import Config

    bind_provider(acp_module, Config.load().llm.provider)
    bind_streams(acp_module, channel)
    acp_module.main()


if __name__ == "__main__":
    main()
