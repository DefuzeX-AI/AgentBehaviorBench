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
