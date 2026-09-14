# TradingAgents in ABB

Official source: https://github.com/TauricResearch/TradingAgents
Revision: `be952b8eccb49720509af544c6675233bc1f10d0` (downloaded 2026-09-14).
Matches Wangyi's recorded source revision. Apache-2.0 license retained in `agent/`.
Upstream code is unchanged; the added `agent/abb-langgraph.json` is ABB loader
metadata. Translation and deployment settings live outside `agent/`.

`bindings/trading.py` maps configured ticker/date and only the current Case Input
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

`YF_DISABLE_CURL_CFFI=1` selects yfinance's upstream requests backend inside this
intercepted deployment. Native curl impersonation returned Yahoo 429 through the
proxy; the native requests backend returned real bars through that same proxy.
No market responses, upstream source code or interception policy are replaced.

Use `smoke-input.json` for native observe. The deployment declares AAPL and
2026-09-11 in `[adapter.context.research_defaults]`, also disclosed in the Agent
Profile. This follows the upstream main.py pattern of configured program
arguments; plain-text Inputs supply the research question. Explicit user JSON
can override ticker/date; invalid explicit fields are rejected. Effective values
are retained as `raw_output.research_request`. Explicit ticker/date overrides
apply to the current Input only; a later plain-text Input uses the deployment
defaults. BBA does not recover fields from older turns or insert prior answers.

One native graph instance and its private writable cache/report/memory directory
remain available throughout the Case, and are released when the Case closes.
The native agent owns any files it writes; BBA does not read them to construct
conversation context. Different Cases use independent directories and instances.

The exposed compiled workflow is a stock-research task entrypoint. It starts a
new graph state for each current request; it does not call the separate native
`propagate()` investment-log lifecycle or promise conversational recall. In
particular, persistent files and repeated Input delivery alone do not establish
multi-turn memory. No bespoke chat, summarization or reflection logic is added.

Historical status: **ready** after actual certification on 2026-09-14. Native execution,
interception, SDK evidence and Judge were accepted. The Finance Case asked for
accounting work outside this deployment, so its behavior score is not evidence
of stock-research quality; that Case-scope limitation is retained in the ledger.
That certification used the former history-replay binding and does not certify
the current-input behavior. Current readiness is recorded in the registry.
Onboarding findings and validation are recorded in
[the campaign](../../../docs/Benchmark-Repair-Campaign.md).

Current-input certification on 2026-09-14 completed one real Input and received
an official Judge report; the registry is now **ready**. The Judge verdict was
`issue` for unsupported claims and missing evidence/citations, with no evidence
gaps. This certifies execution, not research quality or conversational recall.
See [the live record](../../../docs/Agent-Owned-Context-Live-2026-09-14.json).

```bash
agentbench evaluate trading-agents --cases 1 --max-steps 1 --yes --no-view
agentbench certify trading-agents --yes --no-view
```
