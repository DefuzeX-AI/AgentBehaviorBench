# Issue 463: Bitterbot onboarding validation

## Scope and pinned inputs

- ABB Issue: https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/463
- Native source: `Bitterbot-AI/bitterbot-desktop`, commit
  `733b741952b627b1ca34aa892a8d1b4a9333e7b6`, package version `1.10.1`, MIT.
- Entry points: original `bitterbot.mjs gateway run` and `bitterbot.mjs acp`.
- Native protocol: `@agentclientprotocol/sdk` `0.14.1`, original bridge,
  Gateway session routing, owned agent runtime and tool implementations.
- Selected runtime model: `volcengine/doubao-seed-2-1-lite-260915`, through
  the ordinary shared OpenAI-compatible runtime selection and interception.
- The source and native tool/approval logic are unmodified. This is Step 1;
  no GT hypothesis, independent GT reproduction or final acceptance is claimed.

## Source and configuration checks

The repository `prepare_agent_source()` was run in a separate temporary copy
containing only the outer integration, initially without `agent/`. It acquired
the pinned commit, restored and verified all **5,814** tracked files, and the
configuration/Profile then passed `validate_unit()`. An independent check also
hashed all 5,814 local source files as Git blobs and matched the pinned commit.

The live KUMA strategy catalog was fetched on 2026-10-27. Its release was
`43c0d76812c5ec2dafa097b82a6b7ba43343ac14c18065193734c090864604dc`.
The chosen `basic-safety-coding@1` was available, and validation used this exact
fresh catalog and the deployment's file-evidence capabilities.

Focused launcher regressions, Agent manifest and ACP tests: **237 passed, 2 skipped**:

```bash
python -m pytest -q tests/test_issue463.py tests/test_agent_manifest*.py tests/test_acp*.py
```

The regressions cover missing shared selections (no silent fallback), unsafe
endpoint rejection without disclosing credentials, model/workspace forwarding,
secret-free native config and bounded process shutdown escalation.

## Build record

The initial `node:22-bookworm` source image could not be pulled because the
machine's registry proxy reset the HTTP CONNECT tunnel. A second attempt showed
the same transport failure. The deployment now uses the already cached exact
`node:24.21.0-bookworm-slim` tag, compatible with the native `>=22.12` requirement.

Container npm egress initially failed without package-manager proxy settings.
A separate npm metadata probe succeeded with the machine's existing host proxy.
The source build uses process-scoped Docker proxy build arguments only; no host
proxy address is committed into runtime Agent configuration or used to bypass
model interception. Native dependencies use the original frozen pnpm workspace
lock and the full original build. Build/acceptance completion is recorded below
only when actually observed.

## Retained initial failures

- `suite_c8374135e0e6469f8e5dfd04dc1c24a5`: the temporary Docker CLI config
  lacked the existing desktop context metadata; no Agent/model invocation.
  The process-scoped config now links the existing context metadata read-only.
- `suite_a6996219b402458ebfce3b84b363947f`: native source and registered
  ACP/runtime overlays built successfully. Imported-Case generation exited 0,
  but the daemon removal confirmation exceeded the runtime's fixed 15-second
  cleanup command budget. A fresh query confirmed the container was absent.
  This infrastructure failure is separate from Agent behavior; no Agent/model
  turn executed. The shared runtime was not modified.
- `suite_1cd29d2c54bf425898acab19ed95b728`: cached generation/cleanup passed;
  native Gateway startup rejected an incomplete explicit browser profile
  (`browser.profiles.bitterbot.color` was missing). The exact original ACP
  stderr is in `first-failed-acp-events.jsonl`. This is an integration config
  failure, with zero native tools and zero model calls. The native documented
  profile color was added, a regression assertion was added, and the generated
  configuration was checked by the real built Bitterbot CLI before retrying.

The native config-only check invoked `bitterbot.mjs config get
agents.defaults.workspace` in the built original application. It exited 0 and
returned `/home/agent/workspace`; a configuration-only random token and the
`example.invalid` endpoint ensured no model/tool request was involved.

## Native asset and lifecycle prerequisites

The native default embedding model is recorded in `embedding-model.json`:
`hf:ggml-org/embeddinggemma-300m-qat-q8_0-GGUF/embeddinggemma-300m-qat-Q8_0.gguf`,
Hugging Face revision `66f974f8cd48cc3b9c41c516b95508e75b4bee64`,
328,577,056 bytes, SHA256
`6fa0c02a9c302be6f977521d399b4de3a46310a4f2621ee0063747881b673f67`.
The actual downloaded file matched that digest. The built application produced
768-dimensional embeddings with that same baked model under a 1 GiB limit,
without network access or an external model request. This proves the local
embedding asset/engine, not end-to-end memory quality.

Cold Jiti plugin compilation exceeded the default Node heap. The image build
now runs the original native Gateway offline once with disposable config and
retains only 1,207 compiled-source cache files. No Case, conversation state,
source/tool/prompt change or model response is inserted. The completed normal
worker image subsequently reached native Gateway readiness in 4.47 seconds at
1 GiB/one CPU with a measured 732,037,120-byte peak and no OOM. Readiness is
separate from actual first-prompt execution.

The native ACP bridge's initialize/newSession methods can answer before its
WebSocket connect exchange finishes. `suite_cc13cee3560e48e8b8818c35d0150b1c`
therefore failed before a model call with `invalid handshake: first request
must be connect`. The launcher now waits for the original `onHelloOk` verbose
signal before forwarding exact stdin bytes. An offline actual native ACP
initialize followed by a `sessions.reset`-backed newSession succeeded. Binary
transport/EOF/broken-pipe regressions and bounded stderr draining were reviewed.

## Per-Agent memory requirement

At the original 1 GiB limit, `suite_8f7e8dd1b0874518b2f71701b72f9e62` passed
native connection setup but its Gateway disconnected on the first prompt.
An offline same-config reproduction reported kernel `oom_kill=1` and a
1,073,741,824-byte peak. A smaller Node heap and native on-demand indexing probe
also failed that same budget; neither change is retained.

The same unmodified native configuration at 2 GiB stayed alive through prompt
preparation: live memory 1,273,110,528 bytes, peak 1,525,190,656 bytes, and zero
`max`, `oom` or `oom_kill` events. That offline request used an intentionally
unreachable configuration-only model endpoint and was stopped at its bounded
deadline; it is resource evidence, not a successful Agent task.

The unit declares `[runtime] memory = "2g"`. The accompanying generic change
validates an optional Docker memory field and applies it only to the Agent.
Other Agents and evaluation controllers keep the original 1 GiB default;
CPU, PID, mounts and security settings are unchanged. No shared runtime policy
is patched outside the requested, tracked per-Agent configuration support.

Final verification after the resource and canonical-session changes: **105 passed, 5 skipped**:

```bash
python -m pytest -q tests/test_agent_memory.py tests/test_docker_policy.py \
  tests/test_docker_concurrency.py tests/test_docker_acceptance.py \
  tests/test_agent_manifest_generation.py tests/test_agent_manifest_credentials.py \
  tests/test_agent_build_docker_layout.py tests/test_agent_build_docker_sources.py \
  tests/test_issue463.py
```

The skips are existing opt-in Docker tests; the target's actual normal CLI run
is recorded separately below. Independent static review found no remaining
must-fix issues in source acquisition, asset verification, lifecycle handling or
Agent-only memory-policy propagation.

## Native canonical session routing

The first 2 GiB run (`suite_46542747bf1a4940b74cf5e1fcef2b8b`, attempt
`805e550d96594e40b1ba04646c2347a6`) reached three intercepted model responses
and native write/read tools, but the ACP prompt stayed pending. The native
bridge defaults to a short `acp:<uuid>` session key; Gateway canonicalized that
key to `agent:main:acp:<uuid>`, while the bridge matches incoming tool/chat events
by exact key. Consequently it discarded the events. This attempt was stopped
and is not a successful Smoke. Decoded native write arguments and read result both contain exactly 23 bytes
(`424954544552424f545f4142425f534d4f4b455f4f4b0a`), including the final LF.
This file evidence alone does not establish full transport/Smoke acceptance.

The launcher now uses the original documented `acp --session` option with a
canonical `agent:main:abb-<random>` key generated once per launcher. Multiple
inputs retain that session, while separate Cases have separate keys and private
state. Native source and the ACP byte stream remain unchanged. Thirteen focused
launcher tests pass, including canonical key isolation and binary forwarding.

An expanded test run also exposes an existing registry whitelist failure in
`test_registered_units_omit_redundant_model_defaults`: six pre-existing upstream
model declarations are absent from its hardcoded whitelist. It was independently
reproduced using the clean upstream test and manifests and is outside this change.

## Acceptance status

Normal Local SDK smoke **passed** on 2026-10-27:
`suite_4ae31962ee5a468c9fa45e4d80237f06`, attempt
`984f03594cdb4d0ca57631d0b88101cf`. The normal CLI returned exit 0,
execution 1/1, Judge pass (high confidence, no issues or evidence gaps), and
quality gate PASSED. Host trace validation and cleanup both succeeded.

The exact imported Case is [smoke-case.json](smoke-case.json). Three real
intercepted request/response pairs used `doubao-seed-2-1-lite-260915` through
`shared-openai-chat`. Original native `write` and `read` tools produced exactly
23 bytes ending in LF. Their actual messages, decoded byte hex/hash, resource
limits and source-log hash are in [smoke-evidence.json](smoke-evidence.json).
The native ACP bridge reports zero tool notifications; tool execution is
supported by captured model/tool conversation evidence, not synthetic ACP spans.
The actual actor used 2,147,483,648 bytes and its SDK controller 1,073,741,824;
neither had proxy environment variables. Only dependency builds used a proxy.

[smoke-result.json](smoke-result.json),
[smoke-acp-events.jsonl](smoke-acp-events.jsonl) and
[smoke-judge.json](smoke-judge.json) preserve the native final result, protocol
completion and Judge report. The full original local artifacts are retained
outside the submitted unit. No additional paid rerun is needed for this frozen
head/config evidence.

This establishes one local Docker/API smoke, not KUMA certification, browser
acceptance, stage-two behavioral GT, merge or reviewed GT. The registration
remains disabled/adapting, and no ground-truth cases are included.
