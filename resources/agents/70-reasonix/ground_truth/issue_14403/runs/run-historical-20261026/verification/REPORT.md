# Reasonix issue 14403: fresh before/after verification

Date: 2026-10-26 (America/Toronto).

## Verdict

**Correct, with execution-scope qualifications.** Two fresh real Reasonix ACP baseline runs received the verified prompt verbatim and produced one bare LF. A targeted change to `encoding_helpers.go` removed the defect in a fresh ACP run with the same prompt, model, launcher and clean fixture. All three behavioral suites completed. No automated Judge was requested.

The supplied prompt directly covers the single-match literal branch. The replace-all branch is independently confirmed by real Go regression tests. `matchLineEndings` is a contributing early-return path, not the necessary repair site; the successful repair leaves it unchanged.

## Upstream and version

- [Issue 14403](https://github.com/esengine/DeepSeek-Reasonix/issues/14403) genuinely belongs to `esengine/DeepSeek-Reasonix`. Title, exact commit and prompt match GT. Fresh evidence: [upstream-issue.json](upstream-issue.json).
- Tested commit: `a708a88a75302d2ff4391cea6a041c0072ffc618`, detached in `source/`. It merges Studio 2.48.0 release notes; no release-tag mapping is claimed.
- The production unit selects another commit, `2ddc6f646e71eafd415c7168fb7c800e43ee0ccf` / 2.49.0. That binary was not used. Only its unchanged native ACP launcher/model contract was reused.
- Historical source was compiled with Go 1.26.10, CGO disabled, `-trimpath`, parallelism 2. `verify-a708a88` is a custom test build identity, not a release version. Both binary version outputs identify the full tested SHA. See [Dockerfile.build](Dockerfile.build), [build-before.log](build-before.log), [version-before.json](version-before.json), [version-after.json](version-after.json), and [go-build-before.txt](go-build-before.txt).
- Upstream [PR 14404](https://github.com/esengine/DeepSeek-Reasonix/pull/14404) merged at `e29812d38f8aebb24151f983c5e1dbade0181edd`, matching GT. Only its target-file patch was applied to the historical commit; unrelated later changes were not imported. See [upstream-pr.json](upstream-pr.json) and [literal-crlf.patch](literal-crlf.patch).
- Before binary SHA-256: `b05b84907f127ecfcb93a9359f29efe9b05d51e39309330c643cde11ecae70e1`.
- After binary SHA-256: `df49931698ece6702f1a902b6afacf1397cc20c127f638cad0633649d66330fe`.
- Patched host source and actual build-container source share SHA-256 `3a525eeb0cb3e9edfdb88ee655dc659e40360cc6b54dec0f0a2717010b23dc74`.

## Controls and actual execution

[case.json](case.json) preserves the verified one-step prompt exactly. Each case starts a fresh ACP session with a declared fixture, without setup prompts:

```text
[client]\r\nretries=3\r\nbackoff=2\r\n
```

Initial raw SHA-256: `4d2c42c63cc0854ef329ee87158e0f68dd64e50b7baa4fe2a38c30e5fb58c484`. Direct snapshots confirm identical starting bytes for the repeated baseline and repaired run.

All runs use the locally selected OpenRouter `openai/gpt-4.1-mini`, native OpenAI-compatible protocol and balanced profile. First model requests have identical non-message fields, including complete tool definitions, model, stream=true and stream_options.include_usage=true. No temperature or seed was explicitly sent. Native sampling remains nondeterministic. Actual untruncated requests/responses are retained in [before-network.jsonl](evidence/before-network.jsonl), [before-repeat-network.jsonl](evidence/before-repeat-network.jsonl), and [after-network.jsonl](evidence/after-network.jsonl).

Each run makes exactly one successful native `edit_file` call with identical arguments:

```json
{"path":"settings.ini","old_string":"retries=3","new_string":"retries=3\ntimeout=30"}
```

`editFile.Execute` calls `applyOldStringEdit(..., false)` at editfile.go:70. Exactly one literal occurrence in the known fixture necessarily selects the single-match literal branch. Success has no fuzzy-match marker. Subsequent shell commands are only the requested `od -c settings.ini | tail -n 6`; no shell rewrite or alternative writer repairs the file.

| Run | Suite | Execution | Bare LF |
| --- | --- | --- | --- |
| Before | suite_add84df023024637b69a1d29a1eab748 | COMPLETED | 1 |
| Before repeat with raw snapshot | suite_d9b57867fea04136945865d911791336 | COMPLETED | 1 |
| After | suite_34c8c677d2064dbbb062c53f82429e2e | COMPLETED | 0 |

The real `od` command eventually succeeds in all runs. Reasonix initially blocks calls declaring it a verification check as inconclusive; the Agent clears `verifies` and executes it. Native retry counts differ. This unrelated policy behavior was not patched. The repeated baseline additionally calls `complete_step`, which does not write settings.ini.

```text
before: [client]\r\nretries=3\ntimeout=30\r\nbackoff=2\r\n
after:  [client]\r\nretries=3\r\ntimeout=30\r\nbackoff=2\r\n
```

Raw files: [before-settings.ini](evidence/before-settings.ini), 43 bytes; [after-settings.ini](evidence/after-settings.ini), 44 bytes. These are direct reads of the actual temporary workspace, not reconstructions from model text. [capture-before2.log](capture-before2.log) and [capture-after.log](capture-after.log) retain source paths, times, hashes and hex. The read-only [capture_workspace.py](capture_workspace.py) changes no Agent inputs/files.

Calls/results: [before-tools.jsonl](evidence/before-tools.jsonl), [before-repeat-tools.jsonl](evidence/before-repeat-tools.jsonl), [after-tools.jsonl](evidence/after-tools.jsonl). Handshakes and final responses: [before-result.json](evidence/before-result.json), [after-result.json](evidence/after-result.json). Machine-checked controls and all three runs: [verification-summary.json](verification-summary.json), generated by [summarize.py](summarize.py).

## Fault locations and root cause

1. **matchLineEndings, 42–50: supported contributing bypass.** Literal old text causes original old/new text to pass through. This contributes when downstream replacement omits normalization. The helper's documented matching purpose does not require changing it; it remains unchanged in the successful fix.
2. **applyOldStringEdit, 92–105: supported affected replace-all branch.** It uses strings.ReplaceAll without adapting literal replacement endings. The prompt cannot exercise this branch because edit_file passes false. Real Go tests confirm it, including replacements across mixed-ending regions. The native multi_edit entry point was not prompt-tested.
3. **applyOldStringEdit, 144–154: directly confirmed causal location.** Exactly one match uses strings.Replace with raw LF text. Demonstrated Agent arguments select this branch; its repair removes the bare LF.

The core root cause is correct: literal replacements bypass newline adaptation while fuzzy/converted-old paths adapt replacements. Original CRLF bytes survive but the replacement LF is inserted unchanged. The repair routes both literal branches through a helper using the matched line's own terminator, or the previous terminator for an unterminated final line, and records the actual replacement in the receipt. Encoding, fuzzy paths, tools and launcher are unchanged.

`pinned_contains_fix=false` is correct for the tested commit. The fix merge identity is confirmed. First fixed release remains unknown.

## Real Go regression

The upstream regression tests ran against the actual historical package before and after the patch:

```sh
go test -trimpath -p 2 -v -run 'TestLiteralEditKeepsTheLineEndingOfTheLineItLandsIn|TestEditFileLiteralMatchInCRLFFileLeavesNoBareLF' ./internal/tools/builtin
```

Before: 5/9 table cases and the real edit_file disk-write test fail. After: all 9 table cases and the disk-write test pass. Exit codes: 1 and 0. See [probe-before.log](probe-before.log), [probe-after.log](probe-after.log), and [literal_crlf_regression_test.go](literal_crlf_regression_test.go). These supplement, rather than replace, Agent prompt execution. The full project suite was not run.

## Infrastructure and Judge boundaries

Initial suite `suite_5e5c5e917e75443f9aa92625ba2f5465` failed before any model/tool calls because Windows temporary-file paths were too long. Its [before.log](before.log) and before-results directory are preserved and excluded from behavioral conclusions.

Experiment-local [evaluate_longpath.py](evaluate_longpath.py) retains extended Windows paths for host filesystem operations and strips their prefix only for Docker CLI arguments. Both completed arms use this identical host-only adaptation. No shared ABB file or Agent behavior is modified.

First compilation took about 937 seconds; image export was also slow on the shared host. These are infrastructure costs, not Agent defects. No other chat's containers were changed.

All three behavioral suites report exit 0, COMPLETED, 1/1 cases and complete execution evidence. Judge was not requested and quality gates are NOT_EVALUATED. ABB reports `GT matching unavailable (ValueError)`; this is not an automated pass/fail judgment. The conclusion above is the explicit source-path and byte-level verification. Native output did not retain separate final-file exports, so direct snapshots supplement its actual od output.

## Isolation and GT clarification

All experiment source, units, registry, patches, logs and evidence remain under this directory. Production source/configuration, environment file, registry and original GT were untouched. No PR was published.

The GT identity, tested commit and core defect need no correction. [case.suggested.json](case.suggested.json) clarifies causal roles and distinguishes Agent-prompt coverage from independent replace-all regression evidence.
