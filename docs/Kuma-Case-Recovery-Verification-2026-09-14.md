# KUMA preparation and recovery verification

The preparation/recovery implementation was checked against the installed PyPI
`kuma-defuzex==0.2.4`. No paid CaseGen, Agent model, or official Judge request was
made by these checks. This is an implementation verification record, not a claim
that the larger live benchmark campaign has met its acceptance target.

## Host and pinned SDK checks

134 passed; 2 optional container tests skipped in this ordinary invocation:

```bash
.venv/bin/python -m pytest -q \
  tests/test_case_request_recovery.py tests/test_case_preparation.py \
  tests/test_issue7.py tests/test_kuma_pypi.py tests/test_sdk_directory.py \
  tests/test_issue34.py tests/test_issue34_recovery.py \
  tests/test_issue20.py tests/test_issue20_evidence.py
```

These checks cover partial preparation, immutable saved Cases, exact subset
indices, shared generation blocks, ambiguous accepted requests, complete import
validation, public request recovery, original Attempt identity, host evidence
validation, terminal SDK failures, and explicit per-Agent replay declarations.
The tests use the real pinned SDK's offline Case providers/save/reuse and its
public recovery contract; targeted transport fixtures avoid paid service calls.

## Real container checks

The optional container checks were then run explicitly: **6 passed** in total.

The overlay test rebuilt the current BBA runtime into:

```text
defuzex-agentbench/kuma-pypi-acceptance:2a8740a4d7cd14c2be8264105d56d419790313192dc79038ee652581a4751299
```

The runtime was loaded from `/opt/abb-current-runtime`; the SDK was installed
from its pinned PyPI dependency. Case/Agent/Judge execution used `--network none`
and explicit offline providers. It retained Case JSON, the output of a real echo
process, and the real SDK's normalized offline Judge report:

- `results/verification/kuma-pypi-9cbb2db5e4ca47b486235b2da2880a52/verification.json`
- `results/verification/sdk-directory-0b9b4ded1dab41d7ab4c07f3b0f4ec87/`

The directory-adapter test used the rebuilt image, ran two distinct Cases, and
retained one Case/output/Judge/Run artifact set for each Case plus Suite events.

Four Docker acceptance variants additionally exercised two simultaneous Case
workers, normal completion and cancellation, with and without real paired
interceptors. The intercepted upstream was a local test server. Every variant
recorded **zero remaining containers and zero remaining networks**:

- `results/verification/docker-cases-run-24adeac4deff4e2dab5eddf709306eb4/acceptance.json`
- `results/verification/docker-cases-cancel-b4adec268a044105869ef262f76a6feb/acceptance.json`
- `results/verification/docker-cases-paired-run-4bf04e99bfb048ca9f335fd0f9add757/acceptance.json`
- `results/verification/docker-cases-paired-cancel-47ed0d90bd8e4df7bbc0c9f6c71d6b92/acceptance.json`

## Explicit limits

An existing failed Attempt can only accept a recovered report after its original
Case, every Input/output/submission/evidence record, host trace acceptance and
successful cleanup are verified. Older artifacts without those proofs remain
blocked. A terminally failed Judge request is not reopened. An ambiguous CaseGen
request blocks new paid generation until its original disposition is inspected.

`[evaluation] replay_safe = true` was added only to the three configured research
Agents after reviewing their entry points and allowed tools: ReAct's Tavily
search, TradingAgents' market-analysis binding with temporary files and no order
execution, and GPT Researcher's NCBI retrieval binding with MCP disabled. Search
and model usage can still incur charges on a replay. See
[Agent-Replay-Safety.md](Agent-Replay-Safety.md) for the declaration contract.
