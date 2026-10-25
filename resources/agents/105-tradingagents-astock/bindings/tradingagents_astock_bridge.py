"""ABB binding for simonlin1212/TradingAgents-astock (A-share TradingAgents).

Native entrypoint: ``tradingagents.graph.trading_graph.TradingAgentsGraph`` —
graph id ``agent`` in ``install/abb-langgraph.json``. Public
``propagate(company_name, trade_date)`` owns validation, memory, graph
execution and decision recording. This binding constructs that class and
forwards to ``propagate``; it never invokes the inner compiled graph alone.

Boundary adaptations only:
- Input: ``"<TICKER> <YYYY-MM-DD>"`` (e.g. ``"600519 2026-06-01"``), a
  ``{ticker, date}`` object, or natural-language text that names exactly one
  A-share code and one ISO date. Only six-digit A-share codes (optional
  ``.SH`` / ``.SZ`` / ``.BJ`` / ``.SS``) count as tickers; plain English words
  are ignored. ``600519`` and ``600519.SH`` normalise to the same code.
- Config: ``TRADINGAGENTS_*`` and interceptor OpenAI-compatible settings are
  folded into a copy of ``DEFAULT_CONFIG`` at load time (this fork does not
  apply those env keys inside ``default_config.py`` itself).
- Output: ``{"final_state": ..., "decision": ...}`` unchanged from native.
  Ambiguous multi-code prose returns a clarification payload instead of raising.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date
import os
import re


_DATE_RE = re.compile(r"(?<![\d-])(\d{4}-\d{2}-\d{2})(?![\d-])")
# A-share only: six digits, optional exchange suffix. Ignore English words.
_ASHARE_RE = re.compile(r"(?<!\d)(\d{6})(?:\.(?:SH|SZ|BJ|SS))?(?!\d)", re.IGNORECASE)


def _normalize_ashare_code(raw: str) -> str:
    """Strip exchange suffix; keep the six-digit code."""
    text = str(raw).strip()
    m = re.fullmatch(r"(\d{6})(?:\.(?:SH|SZ|BJ|SS))?", text, re.IGNORECASE)
    if not m:
        raise ValueError(
            f"TradingAgents-astock expects a six-digit A-share code "
            f"(optional .SH/.SZ/.BJ), got {raw!r}"
        )
    return m.group(1)


def _ashare_codes_in_text(text: str) -> list[str]:
    """Distinct normalised A-share codes mentioned in ``text`` (order preserved)."""
    seen: list[str] = []
    for match in _ASHARE_RE.finditer(text):
        code = match.group(1)
        if code not in seen:
            seen.append(code)
    return seen


def _explicit_ticker_and_date(text: str) -> tuple[str, str] | str:
    """Parse prose for one A-share code + one date.

    Returns ``(code, date)`` on success, or a clarification string when the text
    names more than one distinct A-share code.
    """
    dates = sorted(set(_DATE_RE.findall(text)))
    codes = _ashare_codes_in_text(text)
    if len(codes) > 1:
        return (
            "Please name exactly one A-share code (six digits, optional "
            f".SH/.SZ/.BJ). Found multiple codes: {', '.join(codes)}."
        )
    if len(dates) != 1 or len(codes) != 1:
        raise ValueError(
            'Supply "<TICKER> <YYYY-MM-DD>", e.g. "600519 2026-06-01", or text that '
            "names exactly one six-digit A-share code and one YYYY-MM-DD date "
            f"(found codes {codes}, dates {dates})"
        )
    return codes[0], dates[0]


def request_from_input(value):
    """Validate explicit ``(ticker, trade_date)`` for ``propagate``.

    Returns ``(ticker, trade_date)`` or a clarification ``str`` when prose names
    multiple distinct A-share codes.
    """
    if isinstance(value, dict):
        if set(value) != {"ticker", "date"}:
            raise ValueError(
                "TradingAgents-astock accepts exactly ticker and date; freeform questions "
                "and extra fields are unsupported"
            )
        ticker, raw_date = value["ticker"], value["date"]
        ticker = _normalize_ashare_code(ticker)
    elif isinstance(value, str):
        parts = value.split()
        if len(parts) == 2 and _DATE_RE.fullmatch(parts[1]):
            # Fast path: "600519 2024-08-30" or "600519.SH 2024-08-30"
            try:
                ticker = _normalize_ashare_code(parts[0])
                raw_date = parts[1]
            except ValueError:
                parsed = _explicit_ticker_and_date(value)
                if isinstance(parsed, str):
                    return parsed
                ticker, raw_date = parsed
        else:
            parsed = _explicit_ticker_and_date(value)
            if isinstance(parsed, str):
                return parsed
            ticker, raw_date = parsed
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
        parsed = request_from_input(value)
        if isinstance(parsed, str):
            return {
                "decision": "NEED_CLARIFICATION",
                "message": parsed,
                "final_state": None,
            }
        ticker, trade_date = parsed
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
