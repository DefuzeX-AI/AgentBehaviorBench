# OpenHarness issue 140: ground-truth verification

Date: 2026-10-26 (America/Toronto).

**Verdict: the two GT code ranges and central root-cause mechanism are correct.** The query branch is the direct fault; the session reconstruction is the propagation location. A missing consumer link should also be recorded. The historical repetition count and exact archived-submission prompt provenance remain independently unverified. A proposed evidence update is provided without changing the original GT.

## 1. Source and version reconciliation

Upstream: [zhijiewong/openharness#140](https://github.com/zhijiewong/openharness/issues/140). The connected GitHub tool fetched the live issue; `upstream-issue.json` preserves its body and metadata. It is open, reports OpenHarness 2.47.0 at `2a7b7b8e1c0b132241d0eebb906dc86863ca19d8`, and describes the same missing-completion-event / orphan-tool-results mechanism. The issue reports ten trials plus a native-stdin control; those are author-reported historical observations, not a count independently reproduced here.

The production integration pins the same revision and DeepSeek provider. The existing `agent/` has no independent Git checkout: `git rev-parse` ascends to the enclosing ABB repository. That enclosing HEAD is not the tested Agent revision. The fixed-commit codeload archive was downloaded into this experiment, and all **546 files** match both the existing source bytes and the cached source-state SHA-256 manifest. `provenance.json` records this comparison and the archive digest. Runtime image probes then compared all 546 original files inside each actual image: baseline has zero changes/missing files; repaired image changes only `src/query/index.ts`. Both report package 2.47.0 and Node v24.22.1. Their compiled `dist/main.js` hashes are identical.

Dependencies were installed with the original `package-lock.json` via `npm ci`; the repair image derives from the baseline and reruns only TypeScript compilation. Actual installed dependency inventories, lockfiles, session source and compiled session executable match between arms. Runtime is Linux Debian bookworm, non-root UID 10001, with Python 3.11.2 and the original native tools. Node base digest: `sha256:6449e19d8184d84062525b6a7524def03146c2cb04a7f08b076680d0e8e4240a`.

The supplied GT's two prompts are not verbatim copies of the live issue: prompt 1 adds `; if a tool fails, state the failure`, and prompt 2 adds `Report the actual changes and test results.` The original archived submission was not located, so its claimed transcription cannot be independently certified. **Both fresh arms use the supplied GT strings exactly**, with no instruction added or removed.

The original `issue-140` GT directory contains only `case.verified.json`; no original raw-run archive is present there or linked from the live issue. The production README retains the historical 10/10 claim but is not a substitute for its underlying traces. No claim is made that an exhaustive search proved the absence of every possible archive elsewhere on the host.

## 2. Original prompts before repair

The original bridge (`bootstrap/session_acp.py`) creates one native process per ACP session and sends successive prompts to that process over NDJSON stdin. Its `launch.prepare` configures the original OpenAI-compatible provider with runtime-owned DeepSeek settings and fresh HOME/XDG state. This experiment imports that unchanged `prepare` function and directly drives the same native `oh session` command, same trust permission policy, and same cross-prompt session continuity. Each arm starts a new container with an empty `/w` workspace and fresh HOME. The workspace mount point differs from the production `/home/agent/workspace`, but is identical across arms.

The configured tested model is **deepseek-chat**, endpoint `https://api.deepseek.com/v1`, as resolved from the repository `.env`. Credentials are passed only through environment variables and never serialized into evidence. The Codex chat model selection does not override the tested Agent model.

The observation preload replaces only the external bootstrap's request observer. It writes the already-serialized request body, response status, and cloned response bytes while forwarding the exact original fetch arguments and original response unchanged. It does not construct tool calls, modify history, call another model, or execute tools. V8 coverage observes actual executable branches without modifying source. No ACP client filesystem/terminal callback or tool substitute participates. The native Agent itself performs all Read/Write/Edit/Bash actions.

Baseline session: `a75f9afc-bca`.

- Prompt 1: two Write calls and two Bash calls succeed. Agent-run assertions verify add and subtract. Four model requests return HTTP 200.
- Persisted first-turn history: user, assistant with **0 toolCalls**, then **4 tool results**.
- Prompt 2: its first model request (`before/request-005.json`) carries those four orphan results and no assistant tool_calls. DeepSeek returns **HTTP 400** with `Messages with role 'tool' must be a response to a preceding message with 'tool_calls'`.
- Native output then reports `No response received`. There is no second-turn success event, no multiply function, and `calculator.py` is byte-identical between `files-1` and `files-2`.

The native process ultimately exits 0 when explicitly asked to exit. That is process lifecycle success, not behavioral success. The driver treats the specific final `No response received` event as the failed prompt boundary because this native error path returns without emitting `turnStop`; it then verifies persistence before exiting.

## 3. Localization and minimal repair

Ranked, falsifiable hypotheses were recorded before intervention in `hypotheses.md`: the query drops completion events; the session independently discards collected calls; or the provider drops correctly persisted calls during serialization. The intervention changes only one original source line: add `yield event;` immediately before the completion branch's break. `minimal.patch` contains the complete change. Neither session code nor provider code is repaired or instrumented.

| GT entry | File, enclosing function and lines | Verdict | Causal role |
| --- | --- | --- | --- |
| 0 | `src/query/index.ts`, `query`, 265–274 | Correct file, branch and range | **Direct fault**: updates internal calls/executor but fails to yield completion to consumers. |
| 1 | `src/main.tsx`, anonymous session command `.action` handler, 804–811 | Correct file, reconstruction block and range | **Propagation**: creates assistant history without calls and still appends results. It remains unchanged when the one-line repair succeeds. |

The GT's `function` strings are descriptive block names, not exported function identifiers. Their meaning is accurate. The actual enclosing functions are identified above. No original range is shown to be mislabeled or unrelated.

Additional locations:

- **Essential missing propagation link:** `src/main.tsx:762–767`, completion-event consumer, is the only `turnToolCalls` population site. Its absence from the location list makes that list less complete, although the Root cause already mentions the consumer.
- **Auxiliary:** `src/main.tsx:740–742`, per-prompt empty accumulator initialization. This is normal setup and does not independently require a repair.
- **Propagation, not a separate demonstrated fault:** `src/providers/openai.ts:35–72`, message conversion. It faithfully serializes absent calls and present results. Actual first-turn internal requests have paired tool calls/results, ruling out a general inability of this provider to serialize calls.

V8 coverage on the actual original-prompt runs supplies a path check:

| Executed block | Before | After |
| --- | ---: | ---: |
| query completion / executor branch | 4 | 10 |
| session `turnToolCalls.push` consumer | 0 | 10 |
| session assistant-history append | 1 | 2 |
| session result-history append | 4 | 10 |

The count 10 after repair covers both prompts combined, not ten trials. Raw V8 coverage and the corresponding compiled executables/source maps are retained. This establishes that the experiment reached the listed code, and that the missing event, rather than an ACP tool bypass, explains the empty consumer.

## 4. Original prompts after repair

Repaired session: `bbac0ea4-446`.

Both prompts complete in that same session, with ten successful native tool actions overall. After prompt 1 the persisted history has **4 assistant calls and 4 matching results**. Prompt 2's first request (`after/request-005.json`) also has four calls and four results, with zero orphan IDs. All eight model requests return HTTP 200, and no native error event appears.

Prompt 2 executes Read/Read/Edit/Edit/Edit/Bash. Its final real Bash output includes:

```text
add(2,3) = 5
subtract(7,4) = 3
multiply(6,7) = 42
ALL ASSERTIONS PASSED
exit=0
```

The saved `calculator.py` contains all three functions; the saved README documents multiply. Independent evaluation of the actual saved calculator bytes confirms all three assertions. These checks supplement the real Agent tool execution; they do not replace the original-prompt comparison.

Controls recorded by `summarize.py`:

- Both prompt arrays exactly match the original GT; each arm retains one native session across both prompts.
- Both start with empty workspaces and fresh independent HOME/XDG directories.
- Model/provider, installed dependencies and lockfile are identical.
- The entire first model request body is **byte-identical** between arms, including the system prompt, tools and user prompt.
- Session source and compiled `dist/main.js` are byte-identical. Original runtime source differs only by the one query yield.

Native model choices are nondeterministic: the tool sequences differ despite identical first requests. This is one fresh before/after pair, not a reproduction-rate estimate.

## 5. Root cause and JSON conclusions

The central causal claims are supported by source, real model traffic, saved history, branch coverage and the one-line intervention: query consumes but does not forward completion; the consumer therefore never fills `turnToolCalls`; reconstruction preserves unmatched results; the provider rejects the next prompt. A successful patch alone would not prove all of this; the recorded intermediate state and coverage establish the chain.

The rest of the Root cause requires narrower attribution. `verdict.json` evaluates every substantive claim separately:

| Claim group | Assessment |
| --- | --- |
| Missing query yield, sole consumer population, unconditional result append | Supported facts for this pinned revision and real native session. |
| Historical ten reproductions plus one native control | Supported as claims in the upstream issue only; old raw trials are not independently certified. |
| No raw traces/archive in the original local collection | Supported for the supplied original GT directory and visible issue attachments; no global filesystem absence claim. |
| No fabricated run directories/counts | Historical collection-methodology statement, not additional runtime evidence. The fresh count here is explicitly one pair. |
| Prompts transcribed from archived submission | Evidence insufficient: original submission unavailable and live issue strings differ slightly. GT strings were nevertheless tested exactly. |
| Organizational case_id | No observed runtime meaning; retained as an identifier. |
| No fresh runtime test during prior organization | Historical scope statement. This later verification supplies new runtime evidence without retroactively proving what the organizer did. |
| Exact first fixing commit unknown | Still unknown. The local patch is not presented as an upstream fix/release. |
| Root case vs other run-local prompts | Cannot independently compare missing original run-local archives. |
| Retained observations are not automatically independent trials | Correct evidence boundary; no historical 10/10 rate is inferred from this experiment. |

**Agent failure is established; infrastructure failure is not the baseline explanation.** The real provider responds with a request-validation error to demonstrably malformed Agent-generated history. Both experiment containers run and shut down normally. No ABB suite or automated Judge was run; this is direct native-path causal verification with the original bridge's invocation and cross-step semantics, not an end-to-end ACP/ABB acceptance result. It neither certifies transport error recovery nor infers Judge correctness from process exit or turn completion.

`case.verified.proposed.json` enriches the evidence, explicitly labels direct versus propagation roles, adds the consumer link, and separates fresh results from historical claims. It preserves the version and exact two prompt strings. `proposal-rationale.md` explains each update. The formal GT, Agent source/configuration, `.env`, registry and shared Git worktree were not modified.

## Artifacts and rerun

All artifacts are under `C:\Song_startup\benchmark\AgentBehaviorBench\tmp\v-openharness-140`.

- `case.original.json`: unchanged original GT snapshot.
- `upstream-issue.json`, `upstream.zip`, `provenance.json`: upstream and source-version evidence.
- `before-image.json`, `after-image.json`, `*-image-probe.json`: actual image identities and source checks.
- `before/` and `after/`: complete native events, raw serialized request bodies, cloned response bytes, per-prompt persisted state, actual file snapshots, coverage and runtime source/executables.
- `verification-summary.json`: traffic/history/file checks, controls and branch counts.
- `verdict.json`: each location, additional locations, each Root cause claim, and execution boundaries.
- `minimal.patch`, `query.fixed.ts`: exact one-line source intervention.
- `case.verified.proposed.json`, `proposal-rationale.md`: optional GT evidence update.
- `artifact-checks.json`, `evidence-index.json`: consistency checks and SHA-256 evidence index.

The scripts retain the experiment method: `prepare.py` obtains the exact source; `Dockerfile` builds the baseline; `patch.py` generates the isolated repair; `Dockerfile.after` compiles it; `run.py before` / `run.py after` run the native two-prompt sessions; `summarize.py` and `finalize.py` evaluate the results. Use the repository host Python with `-X utf8`. Reruns require DeepSeek credentials and Docker permission and must use new arm/output directories to preserve these artifacts. Credentials are not included in any saved artifact.
