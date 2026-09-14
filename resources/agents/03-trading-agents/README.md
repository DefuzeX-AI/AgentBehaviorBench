# TradingAgents in ABB

Official source: https://github.com/TauricResearch/TradingAgents
Revision: `be952b8eccb49720509af544c6675233bc1f10d0` (downloaded 2026-09-14).
Matches Wangyi's recorded source revision. Apache-2.0 license retained in `agent/`.
Upstream code is unchanged; the added `agent/abb-langgraph.json` is ABB loader
metadata. Translation and deployment settings live outside `agent/`.

`bindings/trading.py` maps explicit JSON ticker/date and the Case's conversation
to the native graph. It invokes the compiled graph with process-local callbacks,
so actual model and tool activity reaches ABB/Kuma. There are no fake responses.
The market analyst, bull/bear researchers, trader and risk workflow remain native.
The selected market-only configuration uses yfinance; it does not need FRED or
Alpha Vantage. It never calls a brokerage or places orders.

Use `smoke-input.json` for native observe. First Kuma turn must contain JSON text
with ticker/date/request; later follow-ups may be text. Memory is explicit Case
conversation; temporary native cache/report/memory directories are cleared after
each invocation. A new Case never inherits another Case's state.

Status: **adapting**. Image and boundary validation do not establish certification.
Actual certify is pending a valid OpenRouter key (campaign first run returned 401).
Onboarding findings and validation are recorded in
[the campaign](../../../docs/Benchmark-Repair-Campaign.md).

```bash
agentbench evaluate trading-agents --cases 1 --max-steps 1 --yes --no-view
agentbench certify trading-agents --cases 1 --yes --no-view
```
