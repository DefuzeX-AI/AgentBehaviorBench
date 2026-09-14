# TradingAgents in ABB

Official source: https://github.com/TauricResearch/TradingAgents
Revision: `be952b8eccb49720509af544c6675233bc1f10d0` (downloaded 2026-09-14).
Matches Wangyi's recorded source revision. Apache-2.0 license retained in `agent/`.
Upstream code is unchanged; the added `agent/abb-langgraph.json` is ABB loader
metadata. Translation and deployment settings live outside `agent/`.

`bindings/trading.py` maps configured ticker/date and the Case's conversation
to the native graph. It invokes the compiled graph with process-local callbacks,
so actual model and tool activity reaches ABB/Kuma. There are no fake responses.
The market analyst, bull/bear researchers, trader and risk workflow remain native.
The selected market-only configuration uses yfinance; it does not need FRED or
Alpha Vantage. It never calls a brokerage or places orders.

The upstream `openai_compatible` provider uses Chat Completions, matching ABB's
declared model route. Its `OPENAI_COMPATIBLE_API_KEY` is a container-local virtual
credential; the real provider key stays on the host. Native `openai` instead opts
into `/v1/responses`, which is not this adapter's protocol. Yahoo consent redirects
allow only the observed homepage GETs on `www.yahoo.com` and `ca.yahoo.com` in
addition to finance APIs.

Use `smoke-input.json` for native observe. The deployment declares AAPL and
2026-09-11 in `[adapter.context.research_defaults]`, also disclosed in the Agent
Profile. This follows the upstream main.py pattern of configured program
arguments; plain-text Inputs supply the research question. Explicit user JSON
can override ticker/date; invalid explicit fields are rejected. Effective values
are retained as `raw_output.research_request`. Memory is explicit Case
conversation; temporary native cache/report/memory directories are cleared after
each invocation. A new Case never inherits another Case's state.

Status: **adapting**. Image and boundary validation do not establish certification.
Actual certify is pending a compatible fresh Case and successful native execution.
Onboarding findings and validation are recorded in
[the campaign](../../../docs/Benchmark-Repair-Campaign.md).

```bash
agentbench evaluate trading-agents --cases 1 --max-steps 1 --yes --no-view
agentbench certify trading-agents --yes --no-view
```
