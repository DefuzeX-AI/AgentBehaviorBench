"""ABB LangGraph binding for alphastream's stock-analysis workflow.

Native entrypoint: ``app/agents/coordinator.py:build_analysis_graph(
research_depth=3, selected_analysts=None)`` — it compiles the dynamic
StateGraph(StockAnalysisState): technical analysis always runs, fundamental
and capital-flow analysts run in parallel (depth>=2), sentiment (depth>=3),
a bull/bear debate (depth>=4) and a risk manager (depth>=5), converging on a
decision node.

The binding:

1. Sets ``OPENAI_API_MODEL`` from ``LLM_MODEL`` before importing the app
   (the app reads OPENAI_API_KEY / OPENAI_API_URL / OPENAI_API_MODEL; the
   default URL is api.openai.com, which the harness interception covers).
2. Parses the SDK text into (stock_code, market_type): a 6-digit code is an
   A-share, a 1-6 letter uppercase token is a US ticker, an explicit
   "market=HK|US|A" wins over the heuristic. Missing code is rejected.
3. Compiles the graph once (research_depth=3) and invokes it with
   ``{"stock_code", "market_type", "research_depth", "messages"}``.
"""

from __future__ import annotations

import os
import re
from uuid import uuid4

from langchain_core.runnables.config import RunnableConfig

_CN_CODE = re.compile(r"\b(\d{6})\b")
_US_TICKER = re.compile(r"\b([A-Z]{1,6})\b")
_MARKET = re.compile(r"(?i)market\s*[=:]\s*(A|HK|US)")

_RESEARCH_DEPTH = 3


def _parse_input(text: str) -> tuple[str, str]:
    market_explicit = _MARKET.search(text)
    market = market_explicit.group(1).upper() if market_explicit else None

    cn = _CN_CODE.search(text)
    if cn:
        return cn.group(1), market or "A"
    us = _US_TICKER.search(text)
    if us:
        return us.group(1).upper(), market or "US"
    raise ValueError(
        "No stock code found in the input; pass a 6-digit A-share code or a US ticker symbol"
    )


class AlphastreamAnalysisGraph:
    """Binding wrapper around alphastream's compiled analysis graph."""

    def __init__(self) -> None:
        self._native: object | None = None
        self._closed = False

    def _load_native(self) -> object:
        if self._native is not None:
            return self._native

        model = os.environ.get("LLM_MODEL", "").strip()
        if model:
            os.environ.setdefault("OPENAI_API_MODEL", model)

        from app.agents.coordinator import build_analysis_graph

        self._native = build_analysis_graph(research_depth=_RESEARCH_DEPTH)
        return self._native

    @staticmethod
    def _thread_config(config: RunnableConfig | None) -> dict:
        merged: dict = dict(config) if isinstance(config, dict) else {}
        configurable = dict(merged.get("configurable") or {})
        if not configurable.get("thread_id"):
            configurable["thread_id"] = str(uuid4())
        merged["configurable"] = configurable
        return merged

    def invoke(self, value, config: RunnableConfig | None = None):
        if self._closed:
            raise RuntimeError("AlphastreamAnalysisGraph is closed")

        if isinstance(value, dict):
            text = value.get("input")
            if text is None:
                raise ValueError("Input mapping must contain 'input'")
            extra = set(value) - {"input"}
            if extra:
                raise ValueError(f"Unsupported input fields: {sorted(extra)}")
        else:
            text = value
        if not isinstance(text, str) or not text.strip():
            raise ValueError("input must be a non-empty string")

        stock_code, market_type = _parse_input(text.strip())
        native = self._load_native()

        from langchain_core.messages import HumanMessage

        state = {
            "stock_code": stock_code,
            "market_type": market_type,
            "research_depth": _RESEARCH_DEPTH,
            "messages": [HumanMessage(content=text.strip())],
        }
        return native.invoke(state, config=self._thread_config(config))

    def close(self) -> None:
        self._native = None
        self._closed = True


def create_graph():
    """Zero-argument factory required by the ABB langgraph adapter."""
    return AlphastreamAnalysisGraph()