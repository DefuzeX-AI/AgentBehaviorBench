# ACP adapter implementation and acceptance plan

Status: proposed implementation; ACP support is not yet implemented or certified.
Prepared: 2026-09-19.

## Baseline and objective

ABB was fast-forwarded to upstream `2ece2dc`. Commit `a944ded` allows a writable
Agent container filesystem and executable temporary storage with a 1 GiB tmpfs
limit. Image user identity, capability restrictions, read-only input mounts and
the separate interceptor policy remain in effect. Filesystem ownership still
applies, and tmpfs allocations count toward the container memory limit.

Implement `ACPAdapter` alongside `LangGraphAdapter`, using the existing Case
scheduler, Docker runtime, AgentSession, SDK plugins, evidence pipeline and viewer.
The two real ACP integrations are MiniMax Code and Claude Code, selected by the
user. Claude Code connects through `agentclientprotocol/claude-agent-acp`, which
uses the official Claude Agent SDK; it is not assumed to expose a native
`claude acp` command. Both must use the same ABB adapter without vendor branches.

At each integration milestone, clone its source into the Agent unit's `agent/`
directory and record the revision. Use `MiniMax-AI/minimax-code` for MiniMax and
`agentclientprotocol/claude-agent-acp` for the Claude ACP bridge. For Claude, also
record the installed Claude Agent SDK and runtime versions: cloning the bridge
is not equivalent to obtaining the complete Claude Code runtime source. Keep
outer Docker/configuration/profile files beside the source and pin tested releases.

This document describes planned contracts. Configuration examples are not runnable
until their milestone passes acceptance. Do not mark a registry entry `ready`
based on configuration generation or a protocol handshake alone.

## Existing extension points

| Concern | Existing owner | Planned extension |
| --- | --- | --- |
| Agent invocation | `agentbench/adapter/base.py`, `factory.py` | Register `acp`; retain `AdapterInvocation(output, raw_output)` |
| Case lifetime | `runtime/agentcontainer/session.py` | Own ACP resources through the existing adapter lifecycle |
| Current input delivery | `runtime/agentcontainer/worker.py` | Deliver current input and invocation observation context |
| Process isolation | `runtime/docker/` | Prepare attempt-local workspace and Agent data directories |
| Configuration generation | `onboarding/build_agent_env/` | Adapter-specific render, validation and binding requirements |
| Trace observation | `observe/observers.py`, `invocation.py`, `otel/` | Register ACP event observation and reuse live OTel export |
| Model evidence | `runtime/interception/`, `services/model-interceptor/` | Verify actual child-process traffic and identify correlation gaps |
| Case generation and Judge | `sdk/plugin/kuma/` and `sdk/plugin/local/` | Reuse existing flow; keep protocol logic out of SDK plugins |
| Recovery | `harness/scheduling/`, `harness/session/` | Map classified failures into existing recovery rules |
| Result presentation | `observe/view_api.py`, `web/src/` | Display ACP evidence through existing Case/attempt views |

The existing `framework` field is an adapter dispatch key in this increment.
`acp` describes the invocation protocol, not the Agent's internal implementation.
Do not combine this work with a registry schema migration separating every Agent
architecture dimension.

## Architecture and contracts

```text
Suite scheduler -> Case attempt -> Docker / SDK worker -> AgentSession
                                                         |
                                                   AdapterFactory
                                                   /            \
                                          LangGraphAdapter     ACPAdapter
                                              Python graph     ACP client
                                                                  |
                                                        Agent subprocess
                                                        (e.g. mcode acp)
```

The ACP client, its filesystem/terminal callbacks and Agent subprocess execute
inside the same Case container. They never execute tool requests on the host.
Use the official `agent-client-protocol` Python package for schemas and stdio
transport. Select and pin a tested release after checking ABB's Python support
and the Agent image interpreter. Install adapter dependencies through generic
image/dependency ownership, not KUMA's requirements file. Lazy imports must keep
non-ACP commands usable without the ACP package installed on the host.

Suggested modules, split further only when responsibilities require it:

```text
agentbench/adapter/acp/
  __init__.py
  adapter.py       # Public AgentAdapter implementation
  config.py        # Static configuration and input mapping
  session.py       # Process, negotiation, session and cancellation ownership
  client.py        # Protocol callbacks and negotiated capabilities
  permissions.py  # Explicit allow-once / deny policy
  filesystem.py   # Container-local file callbacks
  terminal.py     # Terminal processes and bounded output
  errors.py       # Structured failure classification
agentbench/observe/acp.py  # Live protocol events -> ABB observation events
```

| Operation | Input | Output and invariant |
| --- | --- | --- |
| `from_agent_dir(root)` | Agent unit containing `agent.toml` | Configured adapter; no network, install or login |
| `load()` | Stored configuration | Static preparation; asynchronous connection setup occurs at first invocation |
| `ainvoke(value, run_config=...)` | Current Case input and local invocation context | `AdapterInvocation`; one active prompt per session |
| `invoke(...)` | Same data for a synchronous caller | Same semantics through a stable event-loop owner |
| `aclose()` / `close()` | Owned adapter resources | Idempotent shutdown of connection, Agent and callback terminals |

Do not create and destroy an event loop per invocation while retaining its process
or connection. Define and test stable ownership for sync and async callers; reject
unsupported mixed-loop usage explicitly. `AgentSession` remains the lifecycle owner.

One Case attempt owns one Agent process and ACP session. Inputs in that attempt
reuse the session; separate Cases and retry attempts get fresh writable state.
Persist the mapping between ABB Case/attempt/input identifiers and ACP session/tool
identifiers. Namespaced identifiers must prevent collisions between sessions.

Protocol sequence: initialize, optional advertised authentication, new session,
optional advertised configuration selection, prompt and streaming updates.
Negotiate capabilities; do not assume `session/close`, load, resume, fork, model
selection or file/terminal callbacks are universally available. Teardown must work
without a protocol close method. Advertise only callbacks actually implemented.
Timeout/cancellation sends protocol cancellation when possible, followed by bounded
process-group cleanup if necessary. Drain stderr independently to prevent deadlocks.

## Configuration, input and installation

Proposed adapter configuration fragment:

```toml
framework = "acp"

[adapter]
type = "acp"
transport = "stdio"
command = ["mcode", "acp"]
cwd = "/workspace"
permission_policy = "allow_once"
```

Use argument arrays without shell interpolation. Framework-specific settings,
input mapping and optional model/auth selection receive validated schemas.
Timeouts inherit existing runtime budgets; expose overrides only for distinct
handshake/cleanup needs and keep them bounded by the attempt budget.

Start with text payloads and explicitly configured extraction from structured
payloads. Reject unsupported input shapes rather than stringifying arbitrary
objects or injecting prior turns. Save original and mapped inputs. Accumulate
assistant message chunks in order for the submitted output; do not concatenate
thoughts, tool diagnostics or stderr into the answer. Keep raw events in append-only
files and return a bounded structured protocol summary with artifact references.

Prepare Agent packages and official protocol wrappers at image build time, with
pinned versions and recorded provenance. No runtime `npx ...@latest` downloads.
MiniMax-specific BYOK configuration belongs to its Agent unit and startup setup,
not vendor-name branches in the shared adapter. Forward declared Agent credentials
without exposing SDK/Judge credentials to the Agent subprocess. Never place secret
values in argv, committed configuration or artifacts.

Onboarding currently assumes `in_process`, a graph descriptor and a Python binding.
Move rendering and validation behind explicit adapter onboarding support. Preserve
LangGraph rules; permit ACP command entrypoints without a dummy Python binding.
Update planning schemas, prompts, validators, dependency instructions and AGENTS.md
to express these adapter-specific requirements. Continue using the existing
add/build/certify flow and SDK-owned Agent Profile/strategy catalog.

### Separate onboarding packages by adapter

User requirement: LangGraph and ACP onboarding must live in separate packages so
that their planning, prompts and validation can be debugged independently. Do not
scatter `if framework == ...` branches across shared builders.

```text
agentbench/onboarding/build_agent_env/
  service.py                  # Shared resumable build orchestration
  common/                     # Checkpoints, writes, redaction and common validation
  frameworks/
    base.py                   # Small onboarding strategy contract
    registry.py               # Explicit strategy lookup
    langgraph/
      planning.py             # Graph selection and required Python bindings
      manifest.py             # LangGraph adapter fields and rendering
      validation.py           # Graph/entrypoint/binding validation
      bindings.py             # Framework-specific binding generation steps
      assets/                 # LangGraph schemas, prompts and examples
    acp/
      planning.py             # Command, installation and protocol requirements
      manifest.py             # ACP adapter fields and rendering
      validation.py           # Command/cwd/input/capability configuration
      assets/                 # ACP schemas, prompts and examples
  planning/                   # Shared request/repair/cache execution
  build_toml/                 # Common manifest envelope and TOML encoding
  build_blinding/             # Reusable file-generation machinery where needed
  build_dockerfile/           # Shared container build constraints and validation
  build_requirement/          # SDK-owned profile generation workflow
```

Each strategy supplies its planning assets/validation, adapter manifest fields,
additional file steps and final adapter validation. Keep identity, credentials,
network policy, persistence, registration and SDK profile ownership in their
existing shared layers. ACP need not implement a binding stage. Shared planners
must select the strategy from validated source evidence or an explicit selection
before using its schema; ambiguous discovery produces an actionable diagnostic.

First extract existing LangGraph rules without changing generated behavior; run
the current onboarding regressions, then add ACP support through the same contract.
Replace the current `build_toml/frameworks.py` implementation with delegation or
migrate its callers; do not retain competing framework registries. Version cached
plans by selected adapter and planning-contract version, revalidate reusable files
and preserve manual edits. Include adapter, stage and file in diagnostic records.

Onboarding acceptance must independently cover LangGraph and ACP, plus shared
checkpoint recovery. LangGraph still requires its valid graph/binding; ACP accepts
a command without graph fields; switching adapters cannot reuse an incompatible
cached plan. Only introduce Docker/profile strategy hooks where actual divergent
requirements exist; do not duplicate the complete onboarding pipeline.

## Writable state and resources

Separate the installed Agent source from the project it is asked to modify.
Runtime prepares an attempt-local writable workspace from a declared fixture,
plus Agent data/cache directories with ownership compatible with the image user.
MiniMax's data-directory setting belongs in its unit configuration.

Keep writable filesystem behavior from `a944ded`. Check HOME, SQLite, native helper
execution, workspace ownership, memory and disk use using the real Agent image.
Do not assume the current 1 GiB memory limit suits every coding Agent; measure
usage and make necessary resource settings generic and explicit.
Save workspace changes needed for evaluation before cleanup. A clean container
alone does not make remote tool side effects replay-safe.

## Evidence, result status and viewer

Write sanitized ACP events and stderr incrementally under the attempt's artifacts.
Record initialization/capabilities, actual selected model, session identity,
permissions, input mapping, final stop reason, exit status and classified errors.
Preserve partial records on failure; bound buffers and record dropped/truncated
content explicitly. Keep protocol summaries and evidence separate from answers.

Feed ACP events live into the existing observation pipeline before each SDK
submission. Tool starts/updates/completions map to real observed spans; partial
updates must merge by tool ID without discarding earlier arguments or outputs.
Unknown extension events remain inspectable. Incomplete or unobserved tool content
must remain marked as such, not fabricated from terminal titles or summaries.
Keep provider/session identity shared with KUMA's existing trace capture.

Python HTTP instrumentation does not automatically instrument Node subprocesses.
Validate model-interceptor routing and TLS trust with real MiniMax traffic. Keep
network evidence separate from ACP observations unless there is a verifiable
correlation ID; never infer causal links from timestamp proximity. A complete
root span alone does not demonstrate complete internal Agent evidence. Report
coverage and host acceptance separately from OTel export success.

`end_turn` is a protocol completion signal, not a passing Judge verdict. Record
execution failure, evidence failure, submission/Judge failure and behavioral findings
separately. Tool failure recovered by the Agent does not automatically fail the
Case. Permission denial is not a transport exception. Unknown stop reasons remain
visible and must not silently become success.

Use existing retry/recovery ownership. Do not automatically replay a prompt after
an uncertain disconnect: the Agent may already have changed files or external
state. Keep `replay_safe` false until the unit's side effects justify otherwise.
Judge recovery must not re-execute completed Agent actions. Reuse existing attempt
states and show the failed attempt alongside any successful retry.

The viewer reuses Case/attempt pages, traces and interaction components. Add only
ACP-specific projections needed to show stop reasons, permissions, tool updates,
capabilities and raw protocol evidence. Preserve unknown/unlinked evidence visibly.

## Delivery milestones and acceptance gates

Each completed milestone receives a focused commit, validation record and push to
the fork. Record skipped or blocked real acceptance separately from passing tests.

| Milestone | Deliverable | Required acceptance |
| --- | --- | --- |
| M1: Protocol lifecycle | Config, adapter registration, process/session management | Real offline stdio fixture verifies handshake, ordered chunks, session reuse, Case isolation, invalid config, failed auth, malformed output, stderr pressure, disconnect, timeout, cancellation and bounded cleanup; sync and async paths work |
| M2: Tools and evidence | Permission/file/terminal callbacks, observer, artifacts | Fixture performs real container file reads/writes and terminal execution; allow/deny are explicit; tools merge partial events correctly; OTel captures actual input/output; failure retains partial evidence; no surviving processes or cross-attempt state |
| M3: Onboarding and MiniMax | Adapter-specific builder rules, pinned MiniMax unit and workspace setup | Static validation and container handshake pass, then real existing certify/evaluate flow captures saved Case, Agent output, model traffic, OTel evidence, SDK submission, Judge report and host acceptance |
| M4: Claude Code and UI | Claude ACP bridge unit, pinned SDK/runtime dependencies, viewer projections | Claude Code works through configuration/unit setup without vendor branches in shared adapter; viewer displays real multi-Case attempts, evidence gaps and temporary failure/retry states; LangGraph regression checks pass |
| M5: Concurrency and recovery | Mixed-suite acceptance artifacts | Five consecutive clean mixed suites meet the matrix below; separate fault-injection runs prove partial persistence, cancellation, retry eligibility and Judge-only recovery |

### Real acceptance matrix

1. MiniMax single Case: inspect every artifact from generation through Judge and
   host acceptance. Use a task fixture that actually requires a tool call; a
   greeting alone cannot validate coding-Agent integration.
2. MiniMax four Cases: verify distinct session IDs, overlapping execution when
   workers allow it, isolated workspaces/data stores and four retained results.
3. Claude Code: independently verify its bridge command, auth, capabilities and
   evidence with at least one real Case before running mixed suites. Validate
   the selected bridge release's permission callbacks and process cleanup.
4. Final clean runs: use MiniMax Code, Claude Code and an existing LangGraph
   Agent. Run five suites with per-Agent Case counts `3, 4, 5, 3, 5` respectively
   (60 Case executions). Require all Cases to complete execution, evidence capture,
   submission, report collection and host acceptance with no infrastructure error.
   Keep behavioral Judge findings visible; do not require every verdict to be pass.
5. Fault injection is separate from the five clean runs: kill an Agent mid-prompt,
   deny a permission, interrupt a transport, fail evidence persistence and simulate
   a retryable Judge request. Completed Cases remain saved; unsafe replay stays
   blocked; eligible retries create new attempts; Judge recovery does not invoke
   the Agent again. A genuine shared persistence failure may stop dispatch while
   preserving already committed results.

Before paid runs, record the remaining campaign allowance and expected test count;
reuse the user's existing quota rather than treating this matrix as a new budget.
If an external quota or SDK failure blocks a gate, retain artifacts, identify the
blocked criterion and consult the relevant official implementation. Do not replace
real Judge results with mock data or mark an unexecuted gate as complete.

### Validation records

For each real run retain the ABB commit, package/image versions, redacted effective
configuration, Case/attempt identifiers, command, result path, execution status,
evidence coverage, Judge status/verdict and host acceptance. Record cleanup and
resource observations. Add regressions for observed failures; use
`tests/test_issue<number>.py` only for a corresponding numbered issue.

Suggested focused suites: adapter protocol/lifecycle, callback tools, observation,
onboarding, opt-in container acceptance and existing LangGraph/session/concurrency
regressions. Use a real local protocol process for transport tests, not exclusively
mock method calls. Run broader relevant checks before final mixed-suite acceptance.

## Deferred scope

Defer ACP registry auto-discovery, remote transports, cross-process session resume,
forked conversations, multimodal inputs and new memory-evaluation design. Preserve
same-Case session continuity as an invocation requirement without introducing a new
memory manager. Do not promise support for an Agent without checking its published
ACP entrypoint or official wrapper and completing its acceptance gates.

## Reference implementations

- ABB baseline: upstream `2ece2dc`; runtime permission change `a944ded`.
- Harbor local review: `73f8bf89`, `src/harbor/agents/installed/acp.py` and
  `acp_runner.py`: installation, capabilities, callbacks and event persistence.
  Its `mcode.py` uses headless `mcode exec`, which is a configuration reference,
  not the generic ACP execution path. Harbor's ATIF conversion does not replace
  ABB's live SDK evidence integration.
- [Official Python ACP SDK](https://github.com/agentclientprotocol/python-sdk).
- [ACP session setup](https://agentclientprotocol.com/protocol/v1/session-setup).
- [MiniMax Code](https://github.com/MiniMax-AI/minimax-code), particularly
  `packages/tui/src/acp/` and `packages/tui/src/cli/run-acp-command.ts`.
- [Claude Agent ACP bridge](https://github.com/agentclientprotocol/claude-agent-acp):
  the ACP integration built on the official Claude Agent SDK. Select the tested
  published package at integration time rather than copying a preview command.

## Current verification record

Only the prerequisite filesystem change has passed tests so far: 30 related tests
and one real offline ReAct-container test, covering native non-root HOME writes,
SQLite, a 65 MiB temporary cache and direct execution of a temporary script.
These results do not establish ACP, MiniMax, Judge or mixed-suite acceptance.

### Implementation checkpoint: protocol lifecycle

- `f9ed87f`: extracted LangGraph onboarding rules and assets into a dedicated
  strategy package; 179 onboarding regression tests passed unchanged in behavior.
- ACP stdio adapter added using `agent-client-protocol==0.12.1`, with lazy SDK
  import, a stable owned event loop, Case-owned session, bounded output, explicit
  auth selection and process-group cleanup. Real offline subprocess tests cover
  sync/async callers, session reuse/isolation, concurrent prompt rejection,
  disconnect, malformed output, timeout, cancellation, descendant cleanup,
  rejected authentication, limits, stderr pressure and input mapping.
- Focused configuration/protocol and existing onboarding/session/concurrency/SDK
  regression selection: 278 passed, 2 opt-in tests skipped. An existing serial SDK
  fixture failed with the user's concurrency setting of 3; this also reproduced
  on baseline `472af04`. Its test now explicitly selects one worker.
- Filesystem/terminal capabilities, ACP onboarding, live evidence, real Agent
  certification and paid mixed-suite acceptance remain pending. No real ACP Agent
  has been marked ready, and no paid Cases have been consumed by these tests.

### M2 implementation checkpoint

ACP filesystem and all terminal callbacks now run inside the Case workspace.
Terminals drain bounded output, preserve UTF-8 boundaries, and are released with
process groups on close. Session permission policy selects allow-once only when
advertised, otherwise denies. Startup notifications are buffered until the returned
session ID is verified. ACP evidence is saved in `acp-events.jsonl` and
`acp-summary.json`; real tool start/update/end notifications project live OTel
spans. Unobserved inputs/results are omitted, not invented. Internal model spans
are not claimed by the protocol observer.

Validation: 55 ACP/protocol/OTel/adapter regression checks passed; 7 viewer tests
passed with loopback permission. An exploratory sweep of all issue tests encountered
missing historical Agent fixtures and sandbox socket restrictions; it is not a
passing full-suite claim. Updated the built-in adapter discovery assertion to
include the newly registered ACP adapter. Real Agent certification remains pending.

### M3 implementation checkpoint

ACP now has its own onboarding package, strict plan/manifest schemas, prompts and
validators. Shared orchestration selects one strategy, prevents framework drift,
fingerprints contracts and preserves resumability. ACP creates no Python graph
binding. Static Node entrypoint/import discovery supplies source evidence. Generic
worker builds stage the registered adapter dependency file, independently of KUMA.
The Docker prompt reflects the actual writable non-root runtime policy.

The imported Claude bridge contains a `CLAUDE.md` file symlink. Build snapshots
now materialize contained regular-file links without changing imported source;
external, broken, cyclic and directory links remain rejected. Regression tests
cover both allowed materialization and rejection boundaries.

Checks: onboarding/manifest/ACP/concurrency selection passed 236 tests before the
source discovery extension; extended onboarding/import selection passed 221 tests
with one test-fixture construction error subsequently corrected. Focused ACP
onboarding/source-link/import regression passed all 17 tests after that correction.
The KUMA image/concurrency subset passed 56 tests, skipped 1, with that same fixture
error in the overlapping ACP test (now corrected). These are offline checks, not
real certification results.

Imported sources: Claude bridge d421f56a6c43cde16d9a7531d08a750a5ef2f04a;
MiniMax Code a5639bcc6146754e01f1ae18bb88545f18299fd6. Units remain unregistered
until their complete configuration is validated.

Final M3 regression rerun after fixture correction: **236 passed, 1 skipped** across
onboarding, manifests, source-link/import rules, KUMA image staging and concurrency.
