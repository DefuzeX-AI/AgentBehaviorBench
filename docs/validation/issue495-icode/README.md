# iCode native ACP acceptance

The unit restores openJiuwen-ai/iCode at `2ced1be715e47be0e789c85af19fde6cda9bdb55`
(0.31.0); all 2,660 restored Git blobs match their original object hashes.
The outer launcher contract tests passed (7 tests), as did the live KUMA Profile
catalog/combined configuration check and a network-disabled native ACP
initialize/session-new check. These checks are distinct from Agent evaluation.

## Real Local Smoke

- Suite: `suite_ed00c3cb36264b5a9acb338528fff97c`
- Attempt: `5becb8453dd045d1a8c3cb6549dd6fe8`
- Model: `deepseek/deepseek-flash`, Chat Completions, `/v1` base.
- One Case, two Inputs, the same native ACP session. The task creates and runs
  `total.py`, then edits, rereads and runs it again, recalling a conversation label.
- Execution, host trace validation and cleanup succeeded; CLI exit 0; local Judge
  pass (high); no evidence gaps. The saved Judge report remains authoritative.
- Observed Agent model requests: 10;
  responses: 8.

There are two retained connection-close errors. Both requests contain the native
session-title generation prompt, while all eight Code Agent requests return HTTP
200. No title feature was disabled. The successful coding task does not establish
that background title generation completed successfully.

The controller ran as WSL root to permit cross-UID workspace cleanup. Agent and
SDK containers remain nonroot. Python is 3.14.8 in both interpreters; the worker's
ACP client is 0.12.1 and the native application's ACP SDK stays
at its pinned 0.10.1 in a separate virtual environment.

## Retained failed deployment checks

The first offline handshake failed because normal iCode startup patches its
Textual installation, which initially belonged to root. Giving the nonroot
Agent ownership of its own native virtual environment fixed that prerequisite.
The first complete Smoke then stopped before inference because the separated
ABB worker lacked its declared OpenTelemetry SDK dependency. That dependency
was added to the worker environment and the Case rerun. Both failure records
are retained; neither is an Agent behavioral defect or a GT candidate.

## Evidence and limits

Original bounded execution/host/Judge/configuration records are copied without
rewriting. `final-replies.json`, `model-traffic-summary.json` and
`tool-events.excerpt.jsonl` are explicitly labeled extracts, not complete traces.
Original full traces and results are retained locally. Hashes in
`acceptance-summary.json` cover the published evidence bytes. Known private
credentials are checked before staging. Git attributes preserve evidence bytes.

This verifies one bounded local task, not every tool or sub-agent. Native
interactive questions need an extension ABB does not implement. No official
KUMA Case generation/Judge call or Credit was used; GT has not been tested.
The integration stays disabled/adapting pending review.
