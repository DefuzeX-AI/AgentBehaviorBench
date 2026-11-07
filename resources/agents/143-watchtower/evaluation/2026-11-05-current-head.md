# Watchtower current-head run — 2026-11-05

Branch head merges main `55a093f94`. The shared model-selection and
interceptor changes (the `ABB_CHAT_THINKING` option and provider handling) were
split out to #561; this branch's diff from main is limited to
`resources/agents/143-watchtower/`, its registry entry and
`tests/test_watchtower_binding.py`. No ABB production source is changed. The
unit moved from slot 113 (now used by main) to 143.

## Checks

- `tests/test_watchtower_binding.py` and the shared model-selection/provider
  tests: pass. The one unrelated failure
  (`test_model_providers.py::...model_override...[local]`, missing
  `LocalRunner.environ`) also fails on unmodified main and is tracked
  separately; it is not touched here.

## Real CLI smoke on unchanged ABB

`agentbench evaluate watchtower --sdk local --case-file
evaluation/local/validation-cases.json --cases 2 --max-steps 1 --timeout 360`
with a temporary enabled registry and the local Judge (`deepseek-chat`). Run
without `ABB_CHAT_THINKING`, so it exercises only what main supports.

- Suite `suite_8e947e3c9da04051884768f4e32cb2c7`. **2/2 completed, quality gate
  PASSED.**
- `watchtower-missing-target` (run `65d99b68fe3144dabcc9fef611c0a544`) and
  `watchtower-invalid-target` (run `14d95b2380c140efae67d9d6e84dec7e`):
  execution `succeeded`, host Trace validation `succeeded`, cleanup `succeeded`.
- Both are input-validation cases. The native agent correctly refuses: "No
  valid URL/IP/domain found in input ... No scan performed", empty
  `scope_targets`, no findings. The Judge returned **pass (high)** for each,
  confirming honest refusal with no fabricated target. No scan traffic or model
  call is expected for a refused input, and none occurred.

## Loopback scan case — documented limitation

The third fixture (`container-loopback.json`, scan `http://127.0.0.1`) still
does not finish within a bounded runtime: it blocked at the 360 s limit, and a
retry at 900 s also timed out at `Docker Agent execution`. The native
planner/worker/analyst loop does invoke the real scanners (subfinder, nmap,
httpx, nuclei, whatweb; amass/dnsrecon unavailable), but the full scan against
container loopback does not complete in bounded time. This reproduces the
2026-10-20 local result and is recorded as a limitation, not promoted to a
pass by extending the limit.

## Status

Fresh current-head smoke on unchanged ABB with native output, trace validation,
host acceptance and Judge receipt, for the two bounded validation cases. The
registry entry stays `enabled = false`, `status = "adapting"`.

Two separate maintainer actions remain outside this branch: merging the shared
#561 changes, and confirming the #365 50-KUMA-Credits approval before any
credited scan acceptance.
