# AgentCrew #504 local execution record

Recorded on October 26, 2026. This is an integration execution record, not a
certification or Ground Truth finding. Upstream source remains unchanged at
`eaff35483b1fea0a856d9e1dd3ce85ace0cf9c04`.

## Implementation and offline verification

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

## Real smoke execution

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

Full acceptance still needs a justified Judge assessment of the complete evidence
and an explicit disposition of the native terminal limitation. KUMA catalog
selection, official certification and GT work remain pending.
The registry remains disabled and adapting.
