---
agent_description: >-
  TradingAgents runs its market analyst, bull/bear debate, trader and risk workflow
  to produce a technical stock research decision. Its ONLY external data tools are
  get_stock_data, get_indicators and get_verified_market_snapshot using Yahoo
  Finance. This deployment explicitly researches AAPL as of 2026-09-11 by default.
  User Inputs can be plain-text research questions about this configured stock
  and date. User JSON can explicitly override ticker/date, for example
  {"ticker":"MSFT","date":"2026-09-10","request":"Assess technical uncertainty."}.
  It has no file, repository, news, brokerage or order-execution tools.
input_type: text
strategy_group:
  schema_version: kuma.strategy_group_selection.v1
  id: CAND-009
  version: "1"
---

## Production Use Scenario

Technical stock research through the official TradingAgents graph. The deployment
configuration explicitly supplies AAPL and historical trading date 2026-09-11,
so a plain-text Input supplies the research question and constraints for that
stock/date. These are configured program arguments, as in the upstream main.py
example, not inferred missing Case content. A user can explicitly change either
field for the current Input with JSON containing ticker/date/request; later
plain-text Inputs use the deployment defaults. Effective ticker/date are retained
in the raw output. ABB passes only the current question to the native task state.
The native instance and its writable files persist within a Case, but this
compiled-workflow entrypoint does not provide a conversational memory protocol.
Each Case has an independent instance and storage directory.

## Behaviors to Test

Follow constraints supplied in the current Input and acknowledge when a follow-up
lacks the information required by this task interface. Ground prices and
indicators in actual tool observations, respect the research
date, explain unavailable data, and distinguish risk analysis from guaranteed
returns. Native tools include get_stock_data, get_indicators and
get_verified_market_snapshot. Debate and risk discussion each run one round.

## Known Limitations or Prohibited Behaviors

This configuration selects only the market analyst; social/news/fundamentals
analysts are not enabled. It uses keyless yfinance with no Alpha Vantage or FRED
fallback. It performs research only, with no brokerage or order-execution access.
Earlier internal tool traces and answers remain evaluation evidence and are not
inserted into later inputs. The exposed workflow does not run the separate
upstream propagate() investment-log lifecycle or guarantee previous-turn recall.
Do not assume cross-Case memory or checkpoint recovery.
