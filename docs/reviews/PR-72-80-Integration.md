# Integration of PRs #72–#80

Reviewed on 2026-09-17 against the maintained fork at `2043f8e` and upstream
`217f74f`. The original series ends at `2ab67ce` and contains eleven commits.
This integration preserves its authorship while adapting selected changes to
the current project. It does not claim every referenced issue is fully resolved.

## What was retained

| PR | Behavior retained | Integration decision |
| --- | --- | --- |
| #72 | Readable invocation inputs; explicit settings/artifact/SDK-ledger permission diagnostics | Exclude global host UID/GID override. Preserve the image's user, HOME and access to its own files. Add real inaccessible-parent regressions. |
| #73 | Propagate transport interruptions without mitmproxy's HTML error page; recover the original Judge request by Run/Case identity | Preserve the existing recovery classifier and scheduler. Compute retryability from the actual upstream status, not a locally synthesized 502. Case-generation recovery is unchanged. |
| #74 | Bootstrap pip in the image's selected Python; mount the SDK repository separately from the Agent source/venv | Keep these SDK-specific changes inside the KUMA plugin. |
| #75 | Distinguish received Judge verdicts from host acceptance; line-buffer CLI output; improve paths, env-file errors and trace diagnostics | Reuse the current terminal presentation and live-Case flow. Also handle inaccessible env-file parents. |
| #76 | Central credential harvesting and normalized credential-field redaction | Exclude the length/numeric filtering heuristic: explicit short or numeric credentials must still be masked. Keep selector words and usage metadata readable. |
| #77 | Honor, validate, route and record the selected KUMA backend; explain SDK import failures | Never echo a rejected credential-bearing URL. Derive the wildcard route under the public `/sdk/` API, supporting a backend at the host root without allowing unrelated paths. |
| #78 | Resolve installed-project paths; model-provider and framework-adapter entry points | Reuse existing runtime provider and adapter contracts. Registration alone does not promise onboarding support or install dependencies into Agent images. |
| #79 | Consistent missing-viewer errors and documentation validation | Preserve the newer English/localized installation and onboarding guides, and the decision to keep one Chinese edition. Add installed-project/plugin guidance instead of restoring obsolete documentation. |
| #80 | Owner-aware repository names, submodules, source discovery/warnings and older LangGraph control-flow compatibility | Reuse one source-warning helper for both initial download and build/certify reuse. No second downloader, builder or registry workflow. |

## Architectural boundaries

- Generic Docker execution shares explicit input mounts and retains image identity;
  it does not know about KUMA ledgers or Judge recovery.
- The KUMA plugin owns backend selection, its SDK overlay/repository and the public
  request-recovery API. No SDK source is vendored or substituted for PyPI.
- Harness results distinguish receipt of a verdict from host acceptance. The CLI
  presents that state; it does not turn retained reports into successful execution.
- Source readiness inspection is shared by download and reuse. The existing
  configuration builder, checkpoints and certification path remain authoritative.
- Project-root lookup and secret harvesting each have one implementation reused
  by their callers. Provider and adapter entry points extend existing interfaces.

## Deliberately incomplete work

The Linux host/container ownership problem is not fully solved. Inputs and
permission diagnostics improve, but private output files and SDK records written
under another UID can still be unreadable on native Linux Docker. A compatible
ownership/transfer design is required; adding a numeric `--user` globally is not
accepted as that design. Do not close #62 or #67 as fully fixed by this integration.

Case-generation request recovery still does not promise a reusable Case or safe
paid regeneration. Judge recovery must resume the original request and retain the
existing identity, evidence and cleanup gates; #69 is only partially addressed.

The wheel still does not bundle the built frontend. Native Linux acceptance and
catalogue-wide framework/onboarding compatibility are not established by the
macOS tests below. Multi-turn memory behavior was not redesigned.

## Validation

Environment: macOS, Python 3.14, Docker Desktop Engine 29.7.2, pinned
`kuma-defuzex[otel]==0.2.7` and `mitmproxy==12.2.3`.

- Baseline suite in a clean worktree: **640 passed, 78 failed, 12 errors, 11 skipped**.
- Integrated suite: **782 passed, 78 failed, 12 errors, 12 skipped**. Failure and
  error identities exactly match the baseline. The existing failures are in old
  Agent/binding fixtures and registry/profile assumptions, including removed units;
  they were not rewritten or hidden by this integration.
- **144 focused PR issue regression tests passed** in the final full suite.
- The real proxy/interceptor suite: **25 passed and 7 subtests passed**, including
  the dropped-connection SDK regression and the HTTP-200 error-body regression.
  These run separately in an isolated environment with service dependencies;
  the host-only suite skips the service test module.
- A real Docker image built the pinned PyPI SDK and saved a Case, Agent output and
  Judge report with offline providers: **1 passed**, network disabled at execution.
- An actual wheel was built and installed outside a checkout. Package imports,
  default registry/env/history/viewer paths, and provider/adapter entry-point
  metadata were verified from a separate project directory.
- The offline CLI demo completed. Its result viewer was not built in the isolated
  integration worktree; the saved result and missing-assets message were retained.

### One production-service acceptance Case

A ReAct evaluation used the existing authorized credentials with `--cases 1
--max-steps 1 --no-view --yes`. It generated one Case, executed the Agent, and
received the official Judge report:

| Layer | Recorded result |
| --- | --- |
| Case execution | `succeeded`, 1/1 completed |
| OTel | `complete` |
| Submission / evidence | `committed` / `captured` |
| Host trace validation / cleanup | `succeeded` / `succeeded` |
| Judge | `issue`, high confidence, no evidence gaps |
| CLI exit | 1, preserving the Judge finding |

Judge reported that the Agent did not complete workspace inspection and
cryptographic verification; it asked for access and file names instead. This
is the received behavioral verdict, not a lost report or infrastructure crash.
This acceptance verifies delivery and preservation of the result; it does not
establish the correctness of the generated scenario or verdict.

Suite: `suite_3537217b3d004094baaf3f706c9f1569`.
Execution artifact: `3170362949e949e9a10ab913bed90595`.
SDK Run: `run_ae9366786068409c846d2e40067f9d16`.
The original artifacts remain in the local integration worktree under
`results/verification/pr72-80-live.json/`; the Suite event log is under the main
checkout's `results/suites/<suite-id>/`. Credentials and full local artifacts are
not included in this PR.
