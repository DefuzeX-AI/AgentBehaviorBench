# Native entrypoint repair

This repair follows the 13-Case audit in
[the mixed-suite review](Live-Mixed-3x5-Issue-Audit-2026-09-14.md).
BBA maintains the SDK plugin and external Agent bindings/configuration. The
vendored native Agent source remains unchanged.

## Stage 1: native API and deployment semantics

- Trading now calls the public `TradingAgentsGraph.propagate(ticker, date)` API.
  Native pending-outcome resolution, investment memory, logging and checkpoint
  cleanup run normally. Current input is never supplied as `past_context`.
- Trading accepts exactly explicit `ticker` and `date` fields, including JSON
  encoded as text. Unsupported research questions are rejected before analysis;
  no constraints are silently discarded and no default stock is inferred.
- Both native public return values are retained as `final_state` and `decision`.
  Detailed reports keep their original field names. The generic adapter and
  KUMA already support JSON output, so their production code did not need changes.
  The OTel allowlist is unchanged.
- GPT uses the supported `write_report(custom_prompt=...)` parameter for a
  requested maximum of 500 words (or a shorter user limit). The old `TOTAL_WORDS`
  setting specified a minimum. Native research context and returned report are
  preserved; no output truncation or case-specific defense was added.
- Profiles, smoke input and onboarding documentation now describe these actual
  contracts. Changed deployments return to `adapting` until certified again.

Tests use `test_issue39_native_trading.py`, `test_issue39_native_research.py` and
`test_issue39_native_output.py`, together with the existing issue regressions.
Full regression: **448 passed, 10 optional tests skipped**. The separate native
Trading run below explicitly enables its Docker test.
The PyPI KUMA test verifies that structured public output reaches immutable
Submission history unchanged while unrelated local diagnostics stay local.

The explicit Trading Docker check passed **16 tests**, including the unchanged
native graph, public lifecycle, memory/reflection and real JSON log writes.
It used image
`defuzex-agentbench/trading-agents:b729cd9f9085a30998494f017465353cba5d2966ab6706b20a344b86dca51106`
with the current binding mounted read-only, network disabled and only external
model/market/price/identity I/O replaced with fixtures. The second same-stock
call received eligible native lessons; a fresh instance did not. Current-round
model/tool callbacks and cleanup were checked.

Native GPT writer tests reproduce the old minimum-length instruction and inspect
the actual replacement model input. A deliberately overlong response is retained
unchanged, proving this is a request to the model rather than a hidden truncation.
These offline checks do not establish model compliance or citation accuracy.

Two read-only official strategy-catalog requests timed out during this stage.
The configured strategy coordinate is retained pending successful catalog review.
No new paid Case or official Judge result is claimed for this stage.

## Remaining acceptance

The previous Trading freeform Cases are incompatible with its corrected native
input contract; do not silently rewrite signed Cases or treat rejection as an
investment-model defect. A fresh official Case must first demonstrate the
documented JSON-text input format. GPT's native metadata parser/compression
limitations and independent model/Judge findings remain open.

The native GPT report-chat REST endpoint has separately passed an offline
feasibility check: its own ReportStore loads and appends conversation history
when given only the current message. Packaging must retain the native frontend
assets required by the application's import. A later stage will connect that
native application lifecycle; Stage 1 still exposes a single research task.

## Stage 2: original GPT report-chat application

Stage 1 was pushed as `1e96bda`. The subsequent external binding now follows the
native frontend's workflow: first generate the report using the original Python
API, POST the actual question/report to `/api/reports`, then POST each current
message to `/api/reports/{id}/chat`. BBA holds the opaque report ID and transport;
the unchanged native app owns the report, history persistence and report RAG.

Each Case constructs a separate original app module with a private native
`REPORT_STORE_PATH`. The temporary environment override is restored immediately
after import. Closing a Case removes its app module and temporary storage.
HTTPX ASGI transport calls the original routes in process; the unrelated
frontend/export web-server lifespan is not started. HTTP 200 error envelopes and
empty chat responses fail the invocation instead of becoming answers. Native
stderr retains the underlying exception.

The image now includes the original frontend files required at app import. Native
chat hardcodes `Config("default")`, so documented environment settings select the
same local embeddings and model provider. No native function is replaced. The
native disabled `quick_search` behavior remains visible; later chat does not
perform new PMC research. The first research question is stored separately and
is not automatically part of chat history; no BBA compensation was added.

Full regression: **452 passed, 11 optional tests skipped**. Explicit native
container acceptance passed again on the rebuilt image in **96.74 seconds**
(the cached-dependency run took 98.47 seconds), with the production default
1 GiB memory, 64 MiB tmpfs, one CPU and read-only `/opt/agent` workdir. Actual PyPI
KUMA, production worker/AgentSession, native research, FastAPI routes, ReportStore,
MiniLM embeddings and native chat ran normally. Only external model/NCBI HTTP
and official Case/Judge services were replaced with clearly local test providers.

- Five-Input Case: native chat recalled and updated its own stored conversation.
- Fresh three-Input Case: no state inherited from the first Case.
- Three-Input failure Case: native model failure returned a failed invocation;
  previous artifacts survived and session/storage cleanup completed.
- Two live AgentSessions: closing one left the other's native memory usable.
- Actual model inputs and emitted model spans verified history and callbacks.
- A separately rebuilt image imported the original app and saved a report with
  no Agent source bind mount, verifying the frontend packaging fix.

The native model helper retries the intentional HTTP 400 failure repeatedly;
this upstream behavior accounts for much of the failure test duration. Its
retry implementation was not changed. These tests establish integration and
state ownership, not real-model correctness or an official passing verdict.
See [the retained acceptance metadata](Native-Entrypoint-Acceptance-2026-09-14.json).

## Official acceptance blocked by connection timeout

A real Trading certification at `1e96bda` took **36.70 seconds** and failed on the
official strategy-catalog GET before any Case was generated or Agent executed.
Direct unauthenticated connection to `defuzex.ai:443` also timed out. No Judge
report or successful Case was produced; the registry remains `adapting`.
[The failure record](Native-Entrypoint-Live-Blocked-2026-09-14.json) retains the
Suite, artifact path, timestamps and error classification.

The retained public catalog identifies `CAND-012@1` as Finance. Trading now
selects that coordinate rather than the general Research group, but its current
availability and generated-input suitability remain unverified during the
outage. A scan of 118 unique stored official Cases found no JSON-object Inputs;
none is suitable for the corrected Trading API. Signed Cases were not edited.

Once the service is reachable, certify the changed deployments, reuse the saved
GPT Cases in fresh Runs for comparison, and then run the mixed three-Agent,
five-Case acceptance. Real citation quality, native metadata omissions and
contradictory Judge clauses remain findings to assess; they were not relabeled
as fixed or passing by these integration changes.
