# SDK integration facilities

SDK plugins receive host facilities through `SDKRunnerContext`. Shared integration
contracts, artifact storage, and the trusted execution client live here. SDK
formats and SDK calls belong in `sdk/plugin/<name>/`; Docker processes, ownership,
mounts and the Agent endpoint belong in `runtime/`.

## Default worker and runner: four business operations

Ordinary SDKs do not need their own runner or worker. Export the concrete
`ContainerSDKPlugin`, which implements the existing `EvaluationSDKPlugin` and
creates the default `EvaluationRunner`. It loads a factory implementing the
existing `SDK.create_run` / `SDKRun` contracts inside the controller container.

Minimal package under `agentbench/sdk/plugin/my_sdk/`:

```text
__init__.py
plugin.py
backend.py
requirements.txt
```

`plugin.py` contains only a declaration; importing it never imports the vendor SDK:

```python
from pathlib import Path
from agentbench.sdk.integration.plugin import ContainerSDKPlugin

plugin = ContainerSDKPlugin(
    create_run=__package__ + ".backend:create_run",
    requirements=Path(__file__).with_name("requirements.txt"),
)
```

Declare SDK-specific inputs with `documents=("requirement.md",)`, credential
names with `worker_environment=("MY_SDK_API_KEY",)`, and network routes with
`whitelist=Path(__file__).with_name("whitelist.json")` when needed. These reuse
the existing image environment and URL whitelist facilities. There is no required
Profile format. Credentials stay in environment variables, outside Case/settings
JSON. Select the package with `agentbench evaluate <agent_id> --sdk my_sdk`.

The SDK business boundary has four operations:

| Operation | Existing contract and responsibility |
| --- | --- |
| Generate/load a Case | `create_run(case=None, ...)` generates; `create_run(case=snapshot, ...)` restores exactly that Case. |
| Get current input | `run.get_input(full=True)` returns `SDKTestInput`, or `None` when finished. |
| Submit this turn | `run.submit(output=..., status=..., error=...)` advances SDK-owned state. |
| Judge | `run.judge()` returns `SDKReport`. An existing `run.report` or final submit return avoids a second Judge call. |

The factory receives `repo_path`, `agent_root`, `storage_path`, `case_index`,
`evidence` and SDK-owned options. `storage_path` is writable controller-private
storage for SDK logs/state; it is separate from the tracked workspace. Runner
options `output` and `timeout` are handled by ABB; remaining `--sdk-options` JSON
keys are forwarded to the factory, including the shared `max_steps` limit.
It returns a Run exposing the existing ID/state/history/report
fields, plus the public `case` generation snapshot. The existing `SDKRun`
declaration now includes `case` and `judge`; custom legacy runners can continue
using their previous get_input/submit/report subset. No parallel Protocol was added.

`integration/run.py` supplies optional concrete `Run`, `Input` and `Report`
implementations. For fixed-input Cases, `Run` already implements get_input and
submit, including submission history. This complete offline `backend.py` only
needs generation and judging:

```python
from agentbench.sdk.integration.run import Run, Report

class EchoRun(Run):
    def judge(self):
        outputs = [step["output"] for step in self.history]
        return Report("pass" if outputs == self.case["expected"] else "issue")

def create_run(*, case=None, case_index=0, evidence=None, **context):
    if case is None:
        # Replace this example with the SDK's generator. context includes the
        # source/workspace path, Agent document root, and SDK request options.
        case = {
            "case_id": f"echo-{case_index}",
            "inputs": [{"input_id": "1", "payload": "hello"}],
            "expected": ["hello"],
        }
    return EchoRun(case, evidence=evidence)
```

The included `smoke` plugin is a runnable two-turn example using these defaults.
It asks the Agent to remember a marker, then recall it in the same session.
Case generation and the exact-match Judge run locally; the selected Agent may
make paid model requests, including its own auxiliary requests:

```bash
agentbench evaluate minimax-code --sdk smoke --cases 1 --max-steps 2 --case-retries 0 --no-view --yes
```

This example requires an onboarded MiniMax Agent and its configured credentials.
See `sdk/plugin/smoke/backend.py` for the only two business methods and
`sdk/plugin/smoke/plugin.py` for the worker/runner declaration.

SDKs with adaptive inputs override get_input and submit, keeping mutable dialogue
state separate from `run.case`. The public snapshot must be a JSON object with a
non-empty `case_id`; its remaining contents belong to the SDK. It must not change
when loaded or during execution. Only the current `SDKTestInput.payload` is sent
to the Agent, with the same Agent session across turns. Neither the complete Case
nor expected answers are mounted in the Agent container. Use `None`, rather than
an empty/falsy test, to distinguish generation from loading a supplied Case.

The default worker saves each generated Case before proceeding to the next. A
committed publication is reused without generating again; incomplete or modified
publications fail for reconciliation. Its artifact envelope binds the SDK factory,
Case slot and workspace. The runner uses the existing `PreparedCase` and artifact
store and validates identity, submitted outputs, trace acceptance and cleanup
before returning `BenchmarkResult`. A Judge pass does not erase Agent failures.

`run.evidence` on the convenience Run points to recorded step directories and
provides `spans()`, which reads original transported OTel spans. A factory may
instead keep this supplied evidence object in its own SDK Run. SDKs decide how
to consume it in submit/judge; no vendor capture schema is required. Execution
errors and partial artifacts remain on disk. The default implementation does not
retry uncertain SDK requests or resume a partially completed dialogue. Persistence
of adaptive inputs provides an audit trail, not a claim of deterministic replay.
Before a generation call it writes a durable start marker in the Case slot. If
no committed Case follows, later preparation stops for SDK request reconciliation
instead of calling generation again. SDK-specific reconciliation belongs in the
plugin; clearing uncertainty is not inferred from an exception or retryable flag.
An optional Run `close()` releases SDK resources after generation or execution.

KUMA uses the same public loop in `integration/dialogue.py` with a plugin-owned
step transaction. Its capture window, submission ledger, file evidence, deferred
Judge and request recovery remain in `plugin/kuma/`. Existing custom workers and
runners remain supported for such SDK-specific lifecycle requirements.

`tests/sdk_fixtures/default_sdk.py` demonstrates all four business operations,
including an input generated from the preceding Agent output. The full acceptance
uses the default worker and runner, rejects KUMA imports, and preserves Case,
Agent outputs, original spans and Judge result:

```bash
ABB_DEFAULT_SDK_IMAGE=<existing-local-image> python -m pytest -q -s tests/test_sdk_defaults.py::test_default_sdk_real_containers
```

## Reuse the existing plugin contracts

An advanced adapter may still export its own `EvaluationSDKPlugin` from
`sdk/plugin/<name>/plugin.py`. Its `create_benchmark_runner(context, options)`
returns an `EvaluationRunner` with `validate_sdk`, `prepare_cases` and `run_case`.
There is no additional registration API or required base class. Optional Case
batch preparation, deferred judging and recovery retain their existing contracts.

Container plugins can now reuse the same execution implementation as KUMA:

- `runtime/docker/evaluation_image.py::evaluation_image` stages the controller
  image and installs the plugin's `requirements.txt`. Plugins declare their worker
  module, worker environment names, required/optional documents and any manifest
  changes for their network routes. No Profile filename or vendor SDK is required.
- `integration/execution.py::run_evaluation` receives the existing
  `SDKRunnerContext` and owns workspace preparation, private storage, the two
  container processes, trace validation, cancellation, diagnostics and cleanup.
- `integration/agent.py::ManagedAgentSession` implements the existing
  `AgentExecutionSession` protocol. It manages invocation artifacts and session
  cleanup while forwarding original spans to the plugin's `EvidenceSink`.

For example, the host side of an existing runner's `run_case` can use:

```python
from functools import partial
from pathlib import Path
from agentbench.runtime.docker.evaluation_image import evaluation_image
from agentbench.sdk.integration.execution import run_evaluation

stage = partial(
    evaluation_image,
    requirements=Path(__file__).with_name("requirements.txt"),
    worker_module=__package__ + ".worker",
)
directory = run_evaluation(
    registration,
    context=self.context,  # SDKRunnerContext received by the plugin factory
    output=self.output,
    stage_agent=stage,
    settings={"case_file": "cases/current.json"},  # This SDK's own settings
    private_files={"cases/current.json": case.artifact_path},
    expected_environment_sha256=case.environment_sha256,
)
# Validate run.json and the SDK's saved report, then return BenchmarkResult.
```

The scheduler-provided `context.job_context` identifies the Case and Attempt.
`context.artifacts` places outputs in that Attempt; without a store the helper
allocates a new directory under `output`. Explicit `context.model` overrides the
environment's Agent model selection without mutating the caller's environment.
Returning an artifact directory is not proof of execution success or a Judge pass.
The plugin remains responsible for interpreting its report and any SDK errors.

For Case generation use `execute_agent=False` and pass `generation_indices` when
the slots are known. Only the controller starts. Case publication remains through
the existing `ArtifactStore` / `CaseArtifacts` protocols. Private file paths are
relative to controller-only storage; they may hold Cases, configuration or judge
data. They never become Agent mounts. A supplied workspace digest is checked before
execution. SDKs requiring a digest for every saved Case additionally set
`require_workspace_identity=True`; private configuration alone does not imply replay.

Inside the worker, use the existing envelope and evidence contracts:

```python
from agentbench.sdk.integration.agent import ManagedAgentSession

async with ManagedAgentSession(output=output, settings=settings) as agent:
    result = await agent.invoke(envelope, step_directory, evidence_sink)
    # Submit result to this SDK while its current-input capture window is open.
```

`envelope` is the normal `abb.invocation.v1` request with a unique invocation
`run_id`, a Case-wide `session_id`, `agent_id`, `framework`, current `input` and
optional `observation_context`. `evidence_sink` implements `accept_span(span)`;
it receives original transported spans before `invoke` returns. The same session
is reused across all inputs. It saves request/result files plus the final session
snapshot and closes even when a turn fails. Custom sessions can be injected with
`session=...` using `AgentExecutionSession`; explicit in-process fixtures use
`InProcessAgentSession`. Production workers must require isolated execution.

Workers still own SDK initialization, input/submission sequencing, report format
and exit status. Publish read access to their output and private storage in a
`finally` block using `sdk.common.output_permissions.share_output`, including on
startup failure. Keep credentials in the declared worker environment, not request
JSON. The shared host excludes those environment names from the Agent process.

See `tests/test_sdk_execution.py` and `tests/sdk_fixtures/independent_worker.py` for
a complete two-turn SDK using these facilities without importing KUMA. The
credential-free Docker acceptance rejects KUMA imports and retains its original
Case, Agent output, spans and Judge result under `results/verification/independent-sdk-*`:

```bash
ABB_INDEPENDENT_SDK_IMAGE=<existing-local-image> python -m pytest -q -s tests/test_sdk_execution.py
```

The local Linux image must contain ABB's runtime dependencies, LangGraph,
OpenTelemetry and a non-root `agent` user. The acceptance inspects the image first
and does not download dependencies or call an external model or Judge.

## Persistent artifacts

The CLI creates the Suite before dispatch. It supplies a `FileArtifactStore`
rooted at that Suite through `SDKRunnerContext.artifacts`, for both fresh runs and
resume. The existing SuiteStore remains the only coordinator state/event writer.
Worker artifact files do not independently change scheduler state.

```python
case = context.artifacts.case(agent_id, case_index)
case.publish_case(original_artifact_bytes)
attempt = case.attempt(attempt_id)
attempt.write_json("steps/0001/result.json", result)
attempt.append_event({"event": "step_finished", "input_id": input_id})
sdk_directory = attempt.private_directory("my-sdk")
```

Implement the structural protocols in `protocols.py` when a different storage
implementation is needed. No evaluator inheritance is required. Directory names
use the existing Agent hash and zero-based Case slot; SDK IDs never become paths.

- Allocate slots before generation. A Case artifact is immutable once published.
- Record each execution under its own Attempt. Never replace previous attempts.
- KUMA generation publishes each accepted artifact directly to its Suite slot,
  before proceeding to the next Case. The generation job retains its original
  diagnostics and collection under `preparation/`.
- Persist current inputs, outputs and errors as execution proceeds. Original span
  exports are retained in the channel response directories even if execution is
  interrupted before the controller collects that step.
- Publish Case bytes before the coordinator emits the prepared event. A hard
  crash between those operations can leave a durable, not-yet-admitted Case;
  a complete KUMA publication is reused without another generation request.
  A torn publication is blocked for repair, never overwritten or regenerated.
- Existing result layouts remain readable. Standalone calls without a Suite
  context retain their original output-root allocation.
- SDK-specific private layouts need not match across plugins. KUMA retains
  `sdk-repo/.kuma` within its run directory so existing request recovery can
  still locate original ledgers.

## Isolation is an execution boundary

A host path alone is not an isolation mechanism. KUMA/local now run the SDK
controller and the Agent endpoint in separate containers. They reuse the built
image but have separate process and filesystem namespaces. The controller mounts
private storage and result output. The Agent mounts its workspace and the
current-input channel; it never mounts the Suite, ledger, profile-generated
Cases, Judge context, or controller output.

The request channel is read-only in the Agent. Each request contains exactly one
current invocation; consumed requests are removed. The Agent keeps one adapter
session for the Case. Only Agent response files flow back, with bounded copying
that rejects links and special files. Neither container receives a Docker socket.
The Agent also does not receive plugin worker credentials.

Each invocation has a default response-copy budget of 1 GiB and 20,000 entries,
including full framework traces and OTel payloads. Large graph state can exceed
the former 128 MiB budget without an unusually large final answer. Configure
`ABB_AGENT_RESPONSE_MAX_BYTES` and `ABB_AGENT_RESPONSE_MAX_FILES` in the host
environment (or CLI `.env`) as positive integers. The trusted controller records
the effective limits in `request/evaluation.json`; these are independent of SDK
submission limits. Copying streams to disk and publishes each file only after
completion. Exceeding a budget still fails explicitly, without truncating evidence
into an apparently complete file or accepting links/special files.

Private writable roots start at mode 0700. Published Case roots retain host
ownership with group write access for the controller, so the host can create
subsequent Attempt directories. The controller uses Python isolated imports
and an ABB code directory outside the writable workspace. A short-lived networkless ownership
helper assigns those explicitly mounted roots to the image's non-root user.
The controller publishes read access to its completed artifacts under the
host-owned private Run directory, retaining host recovery without adding write
access. Agent and controller cleanup are both attempted on every exit path.

The extra controller container consumes its own configured runtime resources.
This change does not alter the existing per-container memory/CPU defaults.

## KUMA adapter

`plugin/kuma/integration.py` is the SDK-specific bridge:

- `storage_options` checks the installed public `storage_path` capability before
  creating a Run. An incompatible SDK fails with upgrade guidance; there is no
  fallback to storing Cases in the workspace.
- Workspace tracking still uses `repo_path`. Private Case/ledger storage uses
  `storage_path`, disjoint from the tracked tree.
- Original ended OTel spans are serialized by the Agent endpoint and decoded
  with their original IDs, timestamps, semantic content and loss counts. The
  KUMA bridge feeds them through public capture methods while the current SDK
  input's capture window is open. Missing transport/evidence remains a failure.
- No Agent graph is imported or invoked by the production SDK controller.
  In-process worker invocation remains only for existing explicit test fixtures;
  the container entrypoint requires isolated execution settings.

Other plugins may adopt these facilities incrementally. A plugin that does not
use the isolated execution interface must not claim its private paths are
inaccessible to its Agent.

## Verification

`tests/test_issue165.py` covers immutable Case bytes, separate attempts, path
boundaries and real OTel/KUMA model content. Set
`ABB_PRIVATE_STORAGE_ACCEPTANCE=1` to run the real Docker acceptance using the
preinstalled local `abb-campaign-validation:local` image. It runs SDK generation,
LangGraph/ACP Agent sessions and an offline custom Judge without API credentials
or paid services. It retains results under `results/verification/issue165-*/`.
