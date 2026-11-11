# AgentCrew #504 validation record

The integration branch is rebased onto upstream main
`be973f1ff` (Watchtower #434). The registry preserves Watchtower and adds
AgentCrew separately at slot 140, disabled and adapting. This PR changes no ABB
production code. The shared Local Judge projection is reviewed in #686; missing
Case identity in Input contexts is fixed separately in #691.

## November 11 follow-up

The rebased integration checks ran independently of the shared production fixes:

```bash
python -m pytest -q tests/test_issue504.py tests/test_agent_manifest_generation.py tests/test_agent_manifest_credentials.py tests/test_sdk_directory.py
```

Result: **72 passed, 1 skipped**. The skip is the opt-in real KUMA container
test; this command does not establish official KUMA service acceptance.

The shared attribution fix restores 5/15 model-to-Input links in the retained
qwen-plus attempt and 6/18 in qwen-flash. Remaining model calls have no recorded
Input link and are not assigned by timestamp or prompt similarity. Both
historical trajectories therefore remain partial. Trajectory status does not
directly determine the quality gate; it remains a separate evidence limitation
raised by the maintainer.

The tightened #686 projection was tested with live positive and negative
controls using the original November 5 requests and hash-verified attachments.
With qwen-flash as Judge, the qwen-flash Agent record received `issue/high`
(51,205 projected characters), while qwen-plus received `pass/high` (52,400).
Neither projection had gaps. These replays are not fresh Agent execution or
this integration's main-only acceptance. See [#686's validation record](https://github.com/EvanTheBoy/AgentBehaviorBench/blob/codex/local-judge-evidence/docs/validation/local-judge-projection/README.md)
for the Judge's explanatory limits and retained source references.

A fresh combined-branch verification uses unchanged integration code plus #686
and #691, with qwen-plus as Agent and qwen-flash as Judge. The model was selected
before execution because its retained run used file tools successfully and
reported terminal restrictions explicitly. This does not guarantee a passing
Judge verdict. Main-only acceptance still requires merging the shared changes,
rebasing this integration again, and rerunning.

## Fresh combined-branch execution (November 11)

This run used combined verification head
`eead21d7472dd4f64e77d51b91fe6ecc5adbd407`: upstream main `be973f1ff`,
rebased #687 integration `df1468017`, #686 production change `d87739b89`,
and #691 production change `482de50bb`. Later validation-document commits do
not change this tested code. No #684 or #685 changes were included.

```bash
TMPDIR=/private/tmp SSL_CERT_FILE=/etc/ssl/cert.pem ABB_LOCAL_JUDGE_MODEL=qwen-flash python -m agentbench evaluate agentcrew --sdk local --model qwen-plus --case-file tests/agent_fixtures/issue504_cases.json --cases 1 --max-steps 3 --no-view -y --env-file /path/to/host-only.env --results-dir /path/to/verification-results
```

AgentCrew alone was temporarily enabled in the combined worktree registry;
the registry was restored byte-for-byte in `finally`. Credentials remained in
the host environment and runtime-owned private configuration. Source preparation
restored and verified 463 pinned files from an empty source directory before the
first attempt, then verified those files again for the successful attempt.

| Dimension | Result |
| --- | --- |
| Suite | `suite_1c1129dce81d4083aaa692a262146bf2` |
| Attempt | `171176ca3b26493ab3251cec834731f7` |
| Agent / Judge models | Bailian `qwen-plus` / `qwen-flash` |
| Inputs | 3/3 completed |
| Host acceptance | Accepted |
| Raw evidence | Complete in manifest; captured in host Case result |
| Host trace validation | Succeeded |
| Cleanup / source cleanup | Succeeded / succeeded |
| Host Judge delivery | Received |
| Judge verdict | Pass, high confidence; no issues or evidence gaps |
| Quality gate / CLI exit | Passed / 0 |
| Projected Judge evidence | 48,456 characters; default 120,000-character cap |
| Derived trajectory | Partial: 10/14 model calls lack confirmed Input attribution |

The trace shows successful file creation and readback in Input 1. In Input 2,
AgentCrew's native validator rejected the terminal request; the Agent then used
`acp_read_file`, computed 21 manually, and disclosed the restriction. Input 3
recalled `Amber Harbor` and 21 and read the file again. No terminal execution
success is claimed. Judge `pass` is the recorded model assessment; it does not
establish that the requested terminal operation happened.

The container manifest says `judge_delivery_status: not_requested` because
judging occurs later on the host. This field alone does not establish that an
execution was a replay. The host `judge/delivery.json` records `received`, and
the host Case result records acceptance and the Judge report. The fresh
execution provenance is recorded independently in `verification.json`.

Artifacts are retained locally under:

`results/verification/issue504-combined-20261111-canonical-tmp/`

The Case, native outputs, tool events, trace, `trajectory.json`, host acceptance,
original Judge response, request and report are retained in the Attempt and Suite.
They are ignored local artifacts, not included in a fresh checkout. The request ID
is `2da7b278775e03a0839c107dc641a1a400cb85b893c9ddc0bb412b4762c5e240`.

An earlier attempt is retained separately under
`results/verification/issue504-combined-20261111/`, Suite
`suite_ea03d3447c374ffd9bf97d8b772b85a6`. It failed during image staging before
Agent execution or judging: the host's noncanonical macOS temporary path
(`/var` resolving to `/private/var`) triggered `Path escapes agent directory: .`.
Setting `TMPDIR=/private/tmp` avoided that confirmed staging defect; it did not
fix the production path-handling code. Both runs remain recorded.

### Remaining acceptance work

This fresh run verifies the combined code only. #687 remains Draft. Main-only
acceptance requires merging the shared dependencies, rebasing #687 onto that
main, and rerunning. Input attribution is still incomplete for model calls
without recorded links; #691 fixes missing Case scope, not those absent links.
The maintainer's Input-attribution concern still needs an explicit disposition.
Official KUMA service assessment, other fresh Agent models, and terminal execution
capability have not been verified by this follow-up.

## November 5 Bailian model retries

Two fresh integration-only CLI runs on ABB main `55a093f94` used Bailian
`qwen-flash` and `qwen-plus` as Agent models, with `qwen-flash` selected for
the Local Judge. Each run produced native output for all three Case inputs.
Host trace validation and cleanup succeeded. ACP records still show the native
terminal refusal. Output receipt does not establish task completion:

- **qwen-flash:** file writing returned `File not found` and the Agent did not
  recover or verify creation. Its second answer labels a file listing
  `Observed Output (if the file is read)`, alongside an explicit terminal
  limitation. Its final answer nevertheless says the value `was read from
  launch-note.txt`, unsupported by the recorded actions. File tools were
  available; the blanket claim of no file access was inaccurate.
- **qwen-plus:** file writing and readback succeeded. Terminal calls were blocked
  by AgentCrew's native policy. The response disclosed that restriction and
  labeled command output as hypothetical (`would output`); a later file read
  verified the content. No terminal command execution success is claimed.

| Agent model | Suite | Attempt | Derived trajectory |
| --- | --- | --- | --- |
| `qwen-flash` | `suite_15e0269b2caa4bd3a15fda0b75d34d9a` | `24a14b66b89e4e95b91cb7406d924f8f` | Partial, 18 model requests lacked confirmed Input attribution |
| `qwen-plus` | `suite_1708fadb20c446d5ab515c66e6fce053` | `7605706ddb3d4fe59fa5713f78f5adc2` | Partial, 15 model requests lacked confirmed Input attribution |

Both Judge receipts were inconclusive because the original Local Judge payload
exceeded its 120,000-character limit. Both quality gates failed. The local
evidence is retained under `results/verification/issue504-split-qwen-flash/` and
`results/verification/issue504-split-qwen-plus/`.

## November 5 integration-only CLI attempt

This attempt used upstream ABB main at `55a093f941fa32120322a80702e91fb1fbb86818`
plus the AgentCrew integration files. Source preparation restored and verified
463 pinned files. The Agent and interception images built, and the CLI delivered
all three Case inputs. Each output contained the configured model endpoint's
HTTP 403 quota error. The derived trajectory is partial, Judge delivery failed,
and the quality gate failed. This attempt does not establish Agent behavior or
terminal capability.

The local Suite is
`results/verification/issue504-split/suites/suite_6997c639433445a3a742eba4ecff0417`.
The corresponding Attempt is
`results/verification/issue504-split/agents/agentcrew/cases/71447b45aa7d51778122bcb8f5c407a5/attempts/57834e1ff75848abbb2d2b6e72127060`.
It retains the Case, the returned error text, the trace and the Judge delivery
record. The Bailian retries above proceeded with available models.

## Historical implementation and offline checks

The following implementation probes and counts predate the split. Current
rebased checks are recorded in the November 11 section above.

The outer launcher runs AgentCrew's native Engineer ACP agent with its original
prompt, tool selection, permission broker, context handling and shutdown. It
maps ABB's selected OpenAI-compatible model to native main, memory, code-analysis
and tool-result-summary clients. Credentials live only in private runtime
configuration. An isolated native environment preserves upstream dependency inputs;
ABB's worker has its own ACP and OpenTelemetry dependencies.

- Clean ABB source preparation restored and verified all 463 pinned source files
  into an empty temporary unit, followed by container and ACP configuration load.
- The real ABB stable ACP client initialized AgentCrew 0.23.0, negotiated protocol
  version 1 and created an Engineer session with networking disabled. The test
  container was removed after cleanup.
- A separate network-disabled native probe verified identical selected model IDs
  across all four clients, the original prompt, 384-dimensional local embeddings,
  Python parsing and Chromium navigation to a local data URL.
- The selected ACP/launcher tests passed: 230 tests. The later manifest/SDK-directory
  selection passed 72 tests with one skipped opt-in real KUMA container test because
  `ABB_SDK_DOCKER_IMAGE` was unset. These selections overlap; do not add the counts.
- Combined static validation and the installed official Profile parser passed.
  A KUMA strategy coordinate has not been selected or verified against a fresh
  catalog. Offline parser acceptance does not establish KUMA service readiness.

## October 28 historical combined-branch result

Suite `suite_afad380dee054ab2a9d7e73d6ac89904` received `pass/high` on combined
#661 head `925a5aa`, which already included shared Local Judge projection
logic. It is retained under `results/verification/issue504-cli-20261028/`.
It is historical combined-branch evidence, not acceptance of #687 on upstream
main. The earlier #504 status based on it must not be read as current acceptance.

## October 26 historical combined-branch execution

The fixed Case is `tests/agent_fixtures/issue504_cases.json`. It requests file
creation/readback, terminal-based reading/calculation and conversation-history
recall with another file verification. The model was the configured Alibaba Cloud
Bailian `deepseek-v4-pro`, routed through ABB's shared native observe integration.

The retained canonical Suite is:

`results/verification/issue504/suites/suite_69b7332d01fd4b5eb313cedea1a2e336`

The execution artifact directory is:

`results/verification/issue504/agents/agentcrew/cases/04be25e3b691527d83cc3eb5bd3b9046/trajectory/7c39318af2d942f6ab1797eea5acee0f`

These are ignored local artifacts, not files included in a fresh Git checkout.
They retain the Case, three Agent outputs, protocol/tool events, model traffic,
OpenTelemetry, host validation, cleanup and the actual Judge result.

| Dimension | Recorded result |
| --- | --- |
| Execution | Completed all three Inputs |
| Host acceptance | Accepted |
| Evidence | Captured |
| Host trace validation | Succeeded |
| Cleanup | Succeeded |
| Local Judge delivery | Received |
| Local Judge verdict | Inconclusive |
| Quality gate | Failed |

The Agent wrote/read the requested file and recalled `Amber Harbor` and `21` in
the final turn. Terminal requests were rejected by native validation, and the
Agent explicitly reported that it had used file reads and arithmetic instead of
executing a successful terminal command. No terminal-success acceptance is claimed.

The runtime recorded 23 model requests, 13 responses and 10 explicit
`Client disconnected.` terminal errors. The trace validator accepted the observed
terminal outcomes; those errors must not be represented as successful responses.
The SDK's per-step OTel evidence and interceptor network events remain separate.

The local Judge stopped at its configured 120,000-character evidence guard.
The complete provider payload measured 830,847 characters. No Judge-model
assessment occurred, and the report explains the limit. Evidence was not silently
truncated or discarded. The original Suite remains inconclusive with a failed
quality gate; an additional assessment must preserve that original report.

## Native terminal limitation

At this pinned revision, `AgentCrew/modules/acp/tools/terminal.py:340` checks
`os.path.abspath(working_dir).startswith(prohibited)` against the Linux path
blacklist. `AgentCrew/modules/command_execution/constants.py:63` includes `/`
in that list. Every absolute Linux working directory therefore matches, including
`/home/agent/workspace`. The recorded permission events show `allow_once`; the
subsequent rejection is in the Agent's validator, before ABB terminal creation.
Even an ordinary `pwd` request was rejected in this run.

The Profile now describes this observed limitation for future evaluation context.
That documentation change does not fix the native validator, add a capability or
alter the frozen Profile/Case in the retained run. No native security check was
patched, bypassed or weakened. This is source-backed diagnosis from one normal
integration run, not an approved GT hypothesis or a ten-run GT reproduction.

## Earlier attempts and remaining work

The first Suite (`suite_3b942e8721e14c7dafcf4e0d6a841025`) stopped before any
Agent model prompt because the isolated ABB worker lacked OpenTelemetry. The
Dockerfile now installs the project's declared OpenTelemetry extra into that
worker interpreter. The second Suite (`suite_3c80a95838684e9784ca7b2246c2c6c9`)
was stopped during an unnecessary embedding download so the build could reuse
its completed model-cache layer. Both earlier attempts remain preserved.

Build logs, mirror measurements, source verification, offline results and reusable
check scripts are under `cache/onboarding/issue-504-preflight/implementation/`.
Regional mirrors were measured from Docker; Tsinghua was used for Debian/security
and direct PyPI for hash-checked Python packages. Dependency locks and TLS/hash
checks remain enabled.

The historical October 26 run remains inconclusive. The November 11 combined
run above has a separate passing Judge receipt; it does not replace that old
result or establish main-only acceptance. KUMA catalog selection, official
certification and GT work remain pending. The registry remains disabled and adapting.
