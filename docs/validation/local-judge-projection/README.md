# Local Judge projection controls — November 11, 2026

The projection change is independent of AgentCrew onboarding. Code under test:
`d87739b89` on `codex/local-judge-evidence`. The request reader uses the shared
`InteractionIndex`, restricted to hash-verified request attachments. Tool records
reference a unique indexed execution by recorded tool call ID within an Input;
timestamps only order the display. Source attachments are never rewritten.

## Verification

```bash
python -m pytest -q tests/test_local_evidence.py tests/test_native_cases.py tests/test_judge_queue.py tests/test_emitted_tool_links.py tests/test_interaction_identity.py
python -m pytest -q tests/test_local_independent.py
```

Results: **29 passed**, then **6 passed**. Regressions cover failed tool results
beside unsupported Agent success claims, equal timestamps with unrelated tool
IDs, exclusion of unverified files, and malformed JSON producing evidence gaps.

Two live replays used the unchanged requests from the November 5 AgentCrew
attempts. Every attachment hash passed validation before submission. The Judge
was the configured Bailian `qwen-flash`; endpoint credentials remained on the
host. Both used the default 120,000-character cap.

| Retained Agent run | Projected characters | Projection gaps | Live Judge |
| --- | ---: | --- | --- |
| `qwen-flash`, attempt `24a14b66b89e4e95b91cb7406d924f8f` | 51,205 | None | `issue`, high confidence |
| `qwen-plus`, attempt `7605706ddb3d4fe59fa5713f78f5adc2` | 52,400 | None | `pass`, high confidence |

The negative assessment cites failed file creation without recovery and an
unverified assumption about file contents. It does **not** specifically identify
the final reply's unsupported assertion that the file was read. Its explanatory
reason also summarizes attempted commands imprecisely. These are model
assessments, not validated Ground Truth findings. The positive assessment accepts
the terminal refusal with an explicit hypothetical result; it does not establish
that a terminal command executed successfully.

Artifacts are retained locally under:

- `results/verification/issue504-686-negative-20261111-final/`
- `results/verification/issue504-686-positive-20261111-final/`

Each includes `verification.json`, the unchanged `judge/request.json`, copied
attachments, `judge/local-evidence.json`, `judge/local-provider.json`, the original
`judge/local-raw-response.json`, and the protocol receipt and report. These ignored
local artifacts are unavailable in a fresh checkout. Earlier draft-prompt replays
are separate under the `20261111-network` suffix; a DNS-blocked replay under
`20261111` has no model verdict. None replaced an original attempt's Judge result.

## Limits

These are replays of existing container evidence, not new Agent executions,
main-branch onboarding acceptance, or official KUMA service verification. They
show that the bounded projection can support different judgments for these two
retained behaviors. They do not measure general Judge sensitivity or accuracy.
