"""\u53ef\u63d2\u62d4\u7684\u591a\u6a21\u6001 LLM \u5ba2\u6237\u7aef\u5c01\u88c5 (\u9879\u76ee\u4e3b\u6846\u67b6\u7248).

\u8bbe\u8ba1\u76ee\u6807:

* \u7528\u6237\u4e0d\u518d\u901a\u8fc7 ``POST /api/ai/analysis`` \u8c03\u6a21\u578b, \u800c\u662f\u76f4\u63a5\u62ff\u5230\u4e00\u4e2a Python \u5bf9\u8c61,
  ``await client.chat(messages)`` \u5c31\u80fd\u62ff\u6a21\u578b\u8f93\u51fa.
* \u9ed8\u8ba4 :class:`QwenVLClient` \u590d\u7528\u9879\u76ee\u91cc\u73b0\u6210\u7684 :mod:`app.modules.ai.service`,
  \u5b83\u4f1a\u4ece :class:`app.core.config.Settings` \u8bfb ``AI_BASE_URL / AI_API_KEY /
  AI_ANALYSIS_MODEL``, \u5bf9\u63a5\u7528\u6237\u914d\u7f6e\u7684\u89c6\u89c9\u8bed\u8a00\u6a21\u578b\u670d\u52a1.
* \u672a\u6765\u60f3\u63a5 OpenAI / Claude / DashScope, \u53ea\u9700\u8981\u5b9e\u73b0\u4e00\u4e2a :class:`LLMClient` \u5b50\u7c7b,
  \u4e0d\u4f1a\u7275\u52a8\u4e0a\u5c42 policy / env \u4ee3\u7801.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

import httpx

from app.core.config import get_settings
from app.modules.ai.service import analysis, parse_model_json

logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    """\u804a\u5929\u63a5\u53e3\u7ea6\u5b9a: \u5582 OpenAI \u98ce\u683c\u7684 messages, \u8fd4\u56de raw content \u5b57\u7b26\u4e32."""

    async def chat(self, messages: list[dict[str, Any]]) -> str: ...


class QwenVLClient:
    """\u9ed8\u8ba4 Qwen-VL \u5b9e\u73b0, \u5185\u90e8\u8c03\u7528\u9879\u76ee\u5df2\u5c01\u88c5\u597d\u7684 ``ai.service.analysis``."""

    def __init__(self) -> None:
        settings = get_settings()
        self.model = settings.ai_analysis_model
        self.base_url = settings.ai_base_url
        self.has_api_key = bool(settings.ai_api_key)

    async def chat(self, messages: list[dict[str, Any]]) -> str:
        return await analysis(messages)


class OpenAIClient:
    """OpenAI / \u517c\u5bb9 OpenAI \u534f\u8bae\u7684\u6269\u5c55\u5b9e\u73b0, \u8d70\u539f\u751f ``chat/completions``."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1/chat/completions",
        timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.timeout = timeout

    async def chat(self, messages: list[dict[str, Any]]) -> str:
        body = {"model": self.model, "messages": messages}
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(self.base_url, json=body, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


def default_llm_client() -> LLMClient:
    """\u6839\u636e\u5f53\u524d Settings \u81ea\u52a8\u9009\u62e9\u9ed8\u8ba4\u5ba2\u6237\u7aef (\u6ca1\u914d key \u65f6\u4e0a\u5c42\u4f1a\u56de\u9000\u5230\u542f\u53d1\u5f0f)."""

    return QwenVLClient()


def parse_action_json(content: str) -> dict[str, Any]:
    """\u5171\u4eab\u7ed9 policy \u7684 JSON \u89e3\u6790, \u590d\u7528 ai.service.parse_model_json."""

    return parse_model_json(content)
