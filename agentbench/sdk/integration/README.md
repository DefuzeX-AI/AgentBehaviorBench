# SDK integration facilities

SDK plugins receive host facilities through `SDKRunnerContext`. Shared integration
contracts, artifact storage, and the trusted execution client live here. SDK
formats and SDK calls belong in `sdk/plugin/<name>/`; Docker processes, ownership,
mounts and the Agent endpoint belong in `runtime/`.

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
