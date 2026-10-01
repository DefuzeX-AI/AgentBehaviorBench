"""Call TradingAgents' public propagate() lifecycle; native code owns the analysis.

Native entrypoint: ``tradingagents.graph.trading_graph.TradingAgentsGraph`` —
graph id ``agent`` in the ABB-added ``abb-langgraph.json``. That class is the
upstream orchestrator, not a compiled graph: its public
``propagate(company_name, trade_date)`` performs the complete task — trade-date
validation, pending-decision settlement, memory past-context retrieval,
instrument-identity resolution, graph execution, decision recording and
checkpoint cleanup — and returns ``(final_state, decision)``. This binding
constructs that class and forwards to ``propagate``; it never invokes the inner
compiled graph directly, because only ``propagate``/``create_run_state`` assemble
the initial state (memory context, resolved instrument identity) the agents
expect. The default stock pipeline is used (``propagate``'s native
``asset_type='stock'`` default); the text input carries no asset type.

Boundary adaptations only:
- Input: the SDK text ``"<TICKER> <YYYY-MM-DD>"`` (e.g. ``"NVDA 2026-09-01"``) or
  the equivalent ``{"ticker": ..., "date": ...}`` object is split into the two
  required native arguments. Ticker path safety uses the native
  ``safe_ticker_component``; the date must be canonical ``YYYY-MM-DD``, and
  ``propagate`` still rejects future dates itself. Freeform questions raise
  ``ValueError``; no field is ever invented or carried over between calls.
- Config: ``propagate`` has no config parameter, so BBA's RunnableConfig
  (callbacks, tags, metadata) is made available to the whole native call through
  LangChain's child-config context (``set_config_context``) rather than dropped
  or serialized. Full observation coverage is assessed during certification.
- Output: the complete native result ``{"final_state": ..., "decision": ...}`` —
  every state field (analyst reports, debate states, ``investment_plan``,
  ``final_trade_decision``, ``final_rating``) and the 5-tier decision
  (Buy/Overweight/Hold/Underweight/Sell, or ``REVIEW`` when the decision had no
  parseable rating). Reports keep their native names; nothing is relabeled or
  synthesized. Native exceptions propagate unchanged as failures.
- Deployment settings arrive exclusively through ``TRADINGAGENTS_*`` environment
  variables folded into ``DEFAULT_CONFIG`` at package import (provider
  ``openai_compatible`` against the configured chat-completions backend, one
  debate and one risk round, and the credential under the
  ``OPENAI_COMPATIBLE_API_KEY`` environment variable name). No endpoint, model or
  key appears in this file; a non-empty adapter context is rejected. The vendor
  chain is the native default (yfinance; sec_edgar,yfinance; fred; polymarket)
  unchanged.

Resources: the wrapper owns only the ``TradingAgentsGraph`` instance it creates
lazily on first invoke; native files live in the natively configured
``~/.tradingagents`` locations. ``close()`` drops the reference and rejects
further invocations, and is safe to repeat. ``propagate`` is synchronous, so no
``ainvoke`` is implemented; BBA's async adapter runs ``invoke`` in a thread.
"""

from copy import deepcopy
from datetime import date
import re


# Evaluation Cases arrive as prose ("Analyze NVDA as of 2026-09-01. ...").
# Accept such text only when it contains exactly one ISO date and the sentence that
# states that date names exactly one ticker-like token; anything ambiguous is
# rejected rather than guessed. Rating words and other common all-caps words are
# not tickers.
_DATE_RE = re.compile(r"(?<![\d-])(\d{4}-\d{2}-\d{2})(?![\d-])")
_TICKER_RE = re.compile(r"(?<![\w$^.=-])\$?(\^?[A-Z][A-Z0-9]{0,5}(?:[.-][A-Z]{1,4}|=F)?)(?![\w.=-])")
_SENTENCE_RE = re.compile(r"(?<=[.!?;])\s+|\n+")
_NOT_TICKERS = frozenset({
    "A", "I", "AI", "API", "LLM", "US", "USA", "UK", "EU", "USD", "EUR", "CEO", "CFO", "ETF", "IPO",
    "SEC", "EDGAR", "FRED", "EPS", "PE", "GDP", "CPI", "Q1", "Q2", "Q3", "Q4", "FY", "YTD", "ISO",
    "JSON", "BUY", "SELL", "HOLD", "OVERWEIGHT", "UNDERWEIGHT", "REVIEW", "OK", "NOT", "NO", "AND",
    "OR", "THE", "YYYY", "MM", "DD", "TICKER", "UTC", "NYSE", "NASDAQ"})


def _explicit_ticker_and_date(text):
    dates = sorted(set(_DATE_RE.findall(text)))
    sentences = [part for part in _SENTENCE_RE.split(text) if dates and dates[0] in part]
    tickers = sorted({t for part in sentences for t in _TICKER_RE.findall(part)
                      if t.lstrip("^") not in _NOT_TICKERS})
    if len(dates) != 1 or len(tickers) != 1:
        raise ValueError(
            'Supply "<TICKER> <YYYY-MM-DD>", e.g. "NVDA 2026-09-01", or text that names exactly '
            f"one ticker and one YYYY-MM-DD date (found tickers {tickers}, dates {dates})"
        )
    return tickers[0], dates[0]


def request_from_input(value):
    """Validate the explicit arguments of the native stock task API.

    Args:
        value: ``"<TICKER> <YYYY-MM-DD>"`` text (the SDK input form) or an
            equivalent ``{"ticker": ..., "date": ...}`` object. Both fields are
            required on every call; no prior value or default ticker is inferred.
    Returns:
        A ``(ticker, trade_date)`` tuple for
        ``propagate(company_name, trade_date)``.
    Raises:
        ValueError: Freeform questions, missing/extra fields, tickers the native
            ``safe_ticker_component`` rejects, or non-canonical dates. Rejected
            input is never silently dropped.
    """
    if isinstance(value, dict):
        if set(value) != {"ticker", "date"}:
            raise ValueError(
                "TradingAgents accepts exactly ticker and date; freeform questions "
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
            'TradingAgents input must be "<TICKER> <YYYY-MM-DD>" text or a '
            "{ticker, date} object"
        )
    if not isinstance(ticker, str) or not ticker:
        raise ValueError("ticker must be a non-empty string")
    from tradingagents.dataflows.symbols import safe_ticker_component

    # Native path-safety validator: rejects empties, path separators, dot-only
    # values and overlong tickers; Yahoo-native symbols like "BTC-USD", "^GSPC"
    # or "GC=F" pass unchanged.
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


class TradingAgentsSession:
    """One constructed native orchestrator and its propagate() calls, until closed."""

    def __init__(self):
        self._native = None
        self._closed = False

    def _load_native(self):
        """Create the native orchestrator once, with the environment-derived config."""
        if self._native is not None:
            return self._native
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        # DEFAULT_CONFIG already folds the TRADINGAGENTS_* environment (provider,
        # models, backend URL, debate/risk rounds, vendor chain) in at package
        # import. A copy keeps the shared default untouched; constructor
        # arguments keep their native defaults, including all four analysts.
        self._native = TradingAgentsGraph(config=deepcopy(DEFAULT_CONFIG), debug=False)
        return self._native

    def invoke(self, value, config=None, *, context=None):
        """Run the public native lifecycle and return both native result values.

        Args:
            value: ``"<TICKER> <YYYY-MM-DD>"`` text or a ``{ticker, date}``
                object, e.g. ``"NVDA 2026-09-01"``.
            config: LangChain RunnableConfig, made available through the
                child-config context so callbacks, tags and metadata observe the
                native graph, tool and reflection calls that ``propagate`` makes.
            context: Must be empty; deployment settings come from
                ``TRADINGAGENTS_*`` environment variables only.
        Returns:
            ``{"final_state": <complete native state>, "decision": <5-tier rating
            or "REVIEW">}``. Analyst reports keep their native names in
            ``final_state``; the decision is never relabeled from an intermediate
            report. No order is executed.
        Raises:
            ValueError: Rejected input, or a future/invalid trade date from
                native validation.
            RuntimeError: Invocation after ``close()``.
            Exception: Native execution errors propagate unchanged; none are
                converted into success-looking answers.
        """
        if self._closed:
            raise RuntimeError("TradingAgents session is closed")
        if context:
            raise ValueError(
                "TradingAgents deployment settings come from TRADINGAGENTS_* "
                "environment variables; adapter context is unsupported"
            )
        ticker, trade_date = request_from_input(value)
        graph = self._load_native()
        from langchain_core.runnables.config import set_config_context

        run_config = dict(config or {})
        # propagate() owns validation, settlement, memory retrieval, graph
        # execution, decision recording and checkpoint cleanup; the child config
        # context observes that entire call without replacing native methods.
        with set_config_context(run_config) as invocation_context:
            final_state, decision = invocation_context.run(
                graph.propagate, ticker, trade_date
            )
        return {"final_state": final_state, "decision": decision}

    def close(self):
        """Release this wrapper's native instance; safe to repeat.

        TradingAgentsGraph exposes no close method in the supplied source, so
        releasing the reference is all this binding owns; native files stay in
        their natively configured locations.
        """
        self._closed = True
        self._native = None


def create_graph():
    """Accept no arguments and return a fresh session owning one native graph.

    Example input: ``"NVDA 2026-09-01"``. The returned mapping's shape (not the
    model's answer) mirrors the upstream run log: ``final_state`` carries
    ``company_of_interest``, ``trade_date``, the analyst reports
    (``market_report``, ``sentiment_report``, ``news_report``,
    ``fundamentals_report``), the debate states, ``investment_plan``,
    ``trader_investment_plan``, ``final_trade_decision`` and ``final_rating``;
    ``decision`` is the 5-tier rating or ``REVIEW``.
    """
    return TradingAgentsSession()
