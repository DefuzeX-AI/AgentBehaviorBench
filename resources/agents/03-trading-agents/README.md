# TradingAgents in ABB

Official source: https://github.com/TauricResearch/TradingAgents
Revision: `be952b8eccb49720509af544c6675233bc1f10d0` (downloaded 2026-09-14).
Matches Wangyi's recorded source revision. Apache-2.0 license retained in `agent/`.
Upstream code is unchanged; the added `agent/abb-langgraph.json` is ABB loader
metadata. Translation and deployment settings live outside `agent/`.

`bindings/trading.py` accepts explicit ticker/date and calls the unchanged public
`TradingAgentsGraph.propagate()` lifecycle. A LangChain child-config context
forwards process-local callbacks to native graph, tool and reflection calls,
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

Use `smoke-input.json` for native observe. The native task accepts an explicit
object such as `{"ticker":"AAPL","date":"2026-09-11"}`. Official Kuma currently
generates text Inputs, so the Profile requires that text to be a JSON-encoded
ticker/date object. Both fields are required on every turn. There is no implicit
stock/date default, freeform request field, chat-message envelope or automatic
field recovery. Unsupported fields/questions fail validation before native work.

One native graph instance and its private writable cache/report/memory directory
remain available throughout the Case, and are released when the Case closes.
The native agent owns any files it writes; BBA does not read them to construct
conversation context. Public `propagate()` now runs the original pending-outcome
resolution, memory retrieval, state logging and decision storage. The original
historical-date rules determine eligible lessons. Pending decisions and future
outcomes are not forced into memory by BBA. Native decision memory is not an
arbitrary chat transcript. Different Cases use independent directories and
instances; no cross-Case memory or process-restart recovery is promised.

The complete public return is exposed as `{"final_state": ..., "decision": ...}`.
`final_state` contains native analyst reports, debate/risk state and the final
portfolio report; `decision` is the native rating signal. BBA neither relabels a
market report as the final answer nor selects only a Hold/Buy/Sell summary.
The native portfolio manager still produces its original investment decision.

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
