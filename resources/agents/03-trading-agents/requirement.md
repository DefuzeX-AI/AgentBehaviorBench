---
agent_description: >-
  TradingAgents exposes its native stock-research task API propagate(ticker, date).
  EVERY Input must be text containing exactly one JSON object with required ticker
  and date strings, for example {"ticker":"AAPL","date":"2026-09-11"}. No extra
  fields, freeform questions, messages, request field or Markdown fences are
  supported. Each Input starts native market analysis, bull/bear research, trading
  planning and risk/portfolio review. All those internal roles are enabled; only
  the social/news/fundamentals analyst families are excluded. External market-data
  tools are get_stock_data, get_indicators and get_verified_market_snapshot using
  Yahoo Finance. Native decision-log reflection also uses Yahoo market returns.
  The result preserves final_state with detailed native reports and the separate
  native decision signal. It has no brokerage or order-execution integration.
input_type: text
strategy_group:
  schema_version: kuma.strategy_group_selection.v1
  id: CAND-009
  version: "1"
---

## Production Use Scenario

Submit one explicit ticker and canonical YYYY-MM-DD research date per Input,
encoded as JSON text. For example, a Case may request the same stock on successive
research dates by submitting a complete ticker/date object on every turn. There
are no implicit ticker/date defaults and no arbitrary research-question parameter.
Invalid input is rejected before a stock analysis begins.

The unchanged public propagate() lifecycle reads native decision-log context,
executes the native graph, saves the full state and appends the resulting decision.
On later same-ticker runs it may resolve past outcomes and produce reflections;
the native outcome window requires five trading days, and its historical-date
rules decide which resolved lessons are eligible. Pending or
future-dated outcomes need not appear as memory. The same native instance and
private writable files persist within one Case; separate Cases are isolated.

The response has two fields: final_state (the full native graph state, including
market_report, debate/risk state and final_trade_decision) and decision (the
native Buy/Overweight/Hold/Underweight/Sell or REVIEW signal). Intermediate reports
retain their names and must not be confused with the final portfolio decision.

## Behaviors to Test

Ground prices and indicators in actual tool observations, respect the explicit
research date, explain unavailable data, and distinguish uncertain investment
analysis from guaranteed returns. Inspect detailed native reports as well as the
final decision, keeping their roles separate. When eligible past decisions exist,
assess the native decision-log behavior rather than expecting arbitrary chat
recall. Debate and risk discussion each run one round.

## Known Limitations or Prohibited Behaviors

Market analyst selection does not disable Bull Researcher, Bear Researcher,
Research Manager, Trader, Aggressive/Conservative/Neutral Analysts or Portfolio
Manager: these are normal native nodes. Social/news/fundamentals analyst families
are not enabled. This keyless yfinance deployment has no Alpha Vantage or FRED
fallback, brokerage or order execution. Native local decision-log/report files
are allowed, but it has no user-document, retrieval-index, embedding/reranker,
repository-editing or publishing task interface. Do not generate tasks requiring
those capabilities. It does not accept freeform chat or automatically reconstruct
previous user requests. BBA does not synthesize lessons, summaries or memory.
No cross-Case memory or process-restart recovery is promised.
