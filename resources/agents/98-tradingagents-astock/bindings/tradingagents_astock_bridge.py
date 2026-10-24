"""ABB binding for simonlin1212/TradingAgents-astock (A-share TradingAgents).

Native entrypoint: ``tradingagents.graph.trading_graph.TradingAgentsGraph`` —
graph id ``agent`` in ``install/abb-langgraph.json``. Public
``propagate(company_name, trade_date)`` owns validation, memory, graph
execution and decision recording. This binding constructs that class and
forwards to ``propagate``; it never invokes the inner compiled graph alone.

Boundary adaptations only:
- Input: ``"<TICKER> <YYYY-MM-DD>"`` (e.g. ``"600519 2026-06-01"``), a
  ``{ticker, date}`` object, or prose that names exactly one ticker-like token
  and one ISO date. A-share 6-digit codes (optional ``.SH``/``.SZ``/``.BJ``)
  are accepted; Chinese names are resolved by native ``safe_ticker_component``.
- Config: ``TRADINGAGENTS_*`` and interceptor OpenAI-compatible settings are
  folded into a copy of ``DEFAULT_CONFIG`` at load time (this fork does not
  apply those env keys inside ``default_config.py`` itself).
- Output: ``{"final_state": ..., "decision": ...}`` unchanged from native.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date
import os
import re


_DATE_RE = re.compile(r"(?<![\d-])(\d{4}-\d{2}-\d{2})(?![\d-])")
# US-style tickers plus A-share 6-digit codes with optional exchange suffix.
_TICKER_RE = re.compile(
    r"(?<![\w$^.=-])("
    r"\$?\^?[A-Z][A-Z0-9]{0,5}(?:[.-][A-Z]{1,4}|=F)?"
    r"|[0-9]{6}(?:\.(?:SH|SZ|BJ|SS))?"
    r")(?![\w.=-])",
    re.IGNORECASE,
)
_SENTENCE_RE = re.compile(r"(?<=[.!?;])\s+|\n+")
_NOT_TICKERS = frozenset({
    "A", "I", "AI", "API", "LLM", "US", "USA", "UK", "EU", "USD", "EUR", "CEO", "CFO", "ETF", "IPO",
    "SEC", "EDGAR", "FRED", "EPS", "PE", "GDP", "CPI", "Q1", "Q2", "Q3", "Q4", "FY", "YTD", "ISO",
    "JSON", "BUY", "SELL", "HOLD", "OVERWEIGHT", "UNDERWEIGHT", "REVIEW", "OK", "NOT", "NO", "AND",
    "OR", "THE", "YYYY", "MM", "DD", "TICKER", "UTC", "NYSE", "NASDAQ", "SH", "SZ", "BJ", "SS",
})


def _explicit_ticker_and_date(text: str) -> tuple[str, str]:
    dates = sorted(set(_DATE_RE.findall(text)))
    sentences = [part for part in _SENTENCE_RE.split(text) if dates and dates[0] in part]
    tickers = sorted({
        t.upper() if t.isalpha() or any(c.isalpha() for c in t) else t
        for part in sentences
        for t in _TICKER_RE.findall(part)
        if t.lstrip("$^").split(".")[0].upper() not in _NOT_TICKERS
    })
    # Prefer bare 6-digit A-share codes when present.
    digit_codes = [t for t in tickers if re.fullmatch(r"[0-9]{6}(?:\.(?:SH|SZ|BJ|SS))?", t, re.I)]
    if len(digit_codes) == 1:
        tickers = digit_codes
    if len(dates) != 1 or len(tickers) != 1:
        raise ValueError(
            'Supply "<TICKER> <YYYY-MM-DD>", e.g. "600519 2026-06-01", or text that names exactly '
            f"one ticker and one YYYY-MM-DD date (found tickers {tickers}, dates {dates})"
        )
    return tickers[0], dates[0]


def request_from_input(value):
    """Validate explicit ``(ticker, trade_date)`` for ``propagate``."""
    if isinstance(value, dict):
        if set(value) != {"ticker", "date"}:
            raise ValueError(
                "TradingAgents-astock accepts exactly ticker and date; freeform questions "
                "and extra fields are unsupported"
            )
        ticker, raw_date = value["ticker"], value["date"]
    elif isinstance(value, str):
        parts = value.split()
        if len(parts) == 2:
            ticker, raw_date = parts
        else:
            ticker, raw_date = _explicit_ticker_and_date(value)
    else:
        raise ValueError(
            'TradingAgents-astock input must be "<TICKER> <YYYY-MM-DD>" text or a '
            "{ticker, date} object"
        )
    if not isinstance(ticker, str) or not ticker:
        raise ValueError("ticker must be a non-empty string")
    from tradingagents.dataflows.utils import safe_ticker_component

    ticker = safe_ticker_component(ticker)
    if not isinstance(raw_date, str):
        raise ValueError("Specify an explicit analysis date as YYYY-MM-DD")
    try:
        trade_date = date.fromisoformat(raw_date).isoformat()
    except ValueError as exc:
        raise ValueError("Specify an explicit analysis date as YYYY-MM-DD") from exc
    if trade_date != raw_date:
        raise ValueError(f"date must be a canonical YYYY-MM-DD value, got {raw_date!r}")
    return ticker, trade_date


def _runtime_config() -> dict:
    """DEFAULT_CONFIG plus ABB interceptor / TRADINGAGENTS_* overrides."""
    from tradingagents.default_config import DEFAULT_CONFIG

    config = deepcopy(DEFAULT_CONFIG)
    provider = os.environ.get("TRADINGAGENTS_LLM_PROVIDER", "openai_compatible")
    backend = (
        os.environ.get("TRADINGAGENTS_LLM_BACKEND_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or "https://api.openai.com/v1"
    )
    model = (
        os.environ.get("TRADINGAGENTS_DEEP_THINK_LLM")
        or os.environ.get("OPENAI_MODEL")
        or os.environ.get("DEEPSEEK_MODEL")
        or "deepseek-chat"
    )
    quick = (
        os.environ.get("TRADINGAGENTS_QUICK_THINK_LLM")
        or os.environ.get("OPENAI_MODEL")
        or os.environ.get("DEEPSEEK_MODEL")
        or model
    )
    config["llm_provider"] = provider
    config["backend_url"] = backend
    config["deep_think_llm"] = model
    config["quick_think_llm"] = quick
    config["max_debate_rounds"] = int(os.environ.get("TRADINGAGENTS_MAX_DEBATE_ROUNDS", "1"))
    config["max_risk_discuss_rounds"] = int(os.environ.get("TRADINGAGENTS_MAX_RISK_ROUNDS", "1"))
    # Keep A-share vendors; do not fall back to yfinance for core data.
    config.setdefault("data_vendors", {})
    for key in (
        "core_stock_apis",
        "technical_indicators",
        "fundamental_data",
        "news_data",
        "signal_data",
    ):
        config["data_vendors"][key] = "a_stock"
    return config


class TradingAgentsAstockSession:
    """One constructed native orchestrator until closed."""

    def __init__(self) -> None:
        self._native = None
        self._closed = False

    def _load_native(self):
        if self._native is not None:
            return self._native
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        # ABB deployment: core three analysts only (skip social/policy/hot_money/
        # lockup) to keep one Case within a bounded time budget.
        self._native = TradingAgentsGraph(
            selected_analysts=["market", "news", "fundamentals"],
            config=_runtime_config(),
            debug=False,
        )
        return self._native

    def invoke(self, value, config=None, *, context=None):
        if self._closed:
            raise RuntimeError("TradingAgents-astock session is closed")
        if context:
            raise ValueError(
                "TradingAgents-astock deployment settings come from TRADINGAGENTS_* "
                "environment variables; adapter context is unsupported"
            )
        ticker, trade_date = request_from_input(value)
        graph = self._load_native()
        from langchain_core.runnables.config import set_config_context

        run_config = dict(config or {})
        with set_config_context(run_config) as invocation_context:
            final_state, decision = invocation_context.run(
                graph.propagate, ticker, trade_date
            )
        return {"final_state": final_state, "decision": decision}

    def close(self) -> None:
        self._closed = True
        self._native = None


def create_graph():
    """Synchronous factory required by ABB LangGraph adapters."""

    return TradingAgentsAstockSession()
