"""ABB LangGraph binding for AlpacaTradingAgent's trading-agents graph.

Native entrypoint: ``tradingagents/graph/trading_graph.py:TradingAgentsGraph``.
Its constructor builds the analyst/debate/risk components and compiles the
LangGraph (``self.graph = self.workflow.compile()``); one full analysis is
``propagate(company_name, trade_date)``.

The binding:

1. Parses the SDK text into (ticker, trade_date). Accepted forms:
   ``ticker=NVDA`` / ``NVDA 2026-10-10`` / any 1-6 letter uppercase token;
   the date defaults to today when absent. Input without a derivable ticker
   is rejected with a clear error.
2. Builds ``TradingAgentsGraph`` once with an OpenAI-compatible config
   (``llm_provider="openai"``, ``backend_url=None`` so the harness
   interception applies), both thinking models set from ``LLM_MODEL``, and
   the yfinance data fallback enabled.
3. Runs ``propagate`` and returns the final state dict.
"""

from __future__ import annotations

import datetime as _dt
import os
import re
from uuid import uuid4

from langchain_core.runnables.config import RunnableConfig

_TICKER_EXPLICIT = re.compile(r"(?i)ticker\s*[=:]\s*([A-Z]{1,6})")
_TICKER_BARE = re.compile(r"\b([A-Z]{1,5})\b")
_DATE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")

# Analysts that work from price/fundamentals data (yfinance fallback enabled).
# Social/news analyst roles need broker/news providers that this deployment
# does not configure.
_ANALYSTS = ["market", "fundamentals"]


def _parse_input(text: str) -> tuple[str, str]:
    ticker_match = _TICKER_EXPLICIT.search(text) or _TICKER_BARE.search(text)
    if not ticker_match:
        raise ValueError(
            "No ticker symbol found in the input; pass a stock symbol such as 'NVDA'"
        )
    ticker = ticker_match.group(1).upper()
    date_match = _DATE.search(text)
    trade_date = date_match.group(1) if date_match else _dt.date.today().isoformat()
    return ticker, trade_date


class AlpacaTradingGraph:
    """Binding wrapper around the compiled trading-agents graph."""

    def __init__(self) -> None:
        self._native: object | None = None
        self._closed = False

    def _load_native(self) -> object:
        if self._native is not None:
            return self._native

        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        model = os.environ.get("LLM_MODEL", "").strip() or "gpt-4o"
        config = dict(DEFAULT_CONFIG)
        config.update(
            {
                "llm_provider": "openai",
                "backend_url": None,
                "deep_think_llm": model,
                "quick_think_llm": model,
                "data_fallback_enabled": True,
                "data_cache_dir": "/tmp/tradingagents/cache",
                "results_dir": "/tmp/tradingagents/results",
                "checkpoint_enabled": False,
                # Optional self-learning memory needs OpenAI embeddings, which
                # this deployment does not route; disable it explicitly.
                "reflection_on_outcome_enabled": False,
                "memory_maintenance_enabled": False,
            }
        )
        graph = TradingAgentsGraph(
            selected_analysts=list(_ANALYSTS), debug=False, config=config
        )
        # Embeddings-dependent reflection memory is an optional feature; this
        # deployment does not route /v1/embeddings, so disable it on the
        # memory objects (the source treats a missing embedding client as a
        # clean no-op). Chat routing is unaffected.
        for attr in (
            "bull_memory",
            "bear_memory",
            "trader_memory",
            "invest_judge_memory",
            "risk_manager_memory",
        ):
            memory = getattr(graph, attr, None)
            if memory is not None:
                memory.embeddings_enabled = False
        self._native = graph
        return self._native

    def invoke(self, value, config: RunnableConfig | None = None):
        if self._closed:
            raise RuntimeError("AlpacaTradingGraph is closed")

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

        ticker, trade_date = _parse_input(text.strip())
        native = self._load_native()

        # Forward the caller's RunnableConfig; propagate() manages its own
        # thread ids when checkpointing is disabled.
        merged: dict = dict(config) if isinstance(config, dict) else {}
        merged.setdefault("configurable", {})
        return native.propagate(ticker, trade_date)

    def close(self) -> None:
        self._native = None
        self._closed = True


def create_graph():
    """Zero-argument factory required by the ABB langgraph adapter."""
    return AlpacaTradingGraph()