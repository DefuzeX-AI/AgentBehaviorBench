# Native cases and independent Judges

ABB can import fixed single- or multi-turn cases, execute an Agent, and save
framework events and OpenTelemetry spans without installing `kuma-defuzex` or
providing KUMA credentials. Select `native` explicitly; existing `kuma`, `local`
and `smoke` saved result formats remain supported. New `local` runs use native ABB execution.

## Execute a case

Create `cases.json`:

```json
{
  "schema": "abb.cases.v1",
  "cases": [{
    "case_id": "memory-001",
    "inputs": [
      {"input_id": "remember", "payload": "Remember the word blue."},
      {"input_id": "recall", "payload": "What word did I ask you to remember?"}
    ]
  }]
}
```

```powershell
agentbench evaluate AGENT_ID --sdk native --case-file cases.json --cases 1 --max-steps 2
```

Payloads are the selected Agent's native JSON input, not automatically converted
chat messages. Check its binding/input contract. Input IDs must be unique within
each case, and case IDs must be unique within the collection. The case count must
match `--cases` (or the registry count); the step budget must cover every input.
ABB does not silently truncate cases. An execution failure stops that case and
records the remaining input IDs without executing them in a damaged session.

The native plugin imports the collection locally, then uses the shared container
preparation/execution machinery to freeze cases, preserve workspace identity,
and isolate the Agent from controller data. No case-generation model is called.
One case retains one Agent session. Different cases retain isolated sessions.
Workspace fixtures are configured through the existing Agent manifest policy.

Results use the existing Suite/Agent/Case/attempt layout. No Judge creates no
fake passing report: `judge_delivery_status=not_requested`, report is null, and
the quality gate is `not_evaluated`. Successful execution-only suites exit zero.
`reuse` can rerun the saved case without its original import file. Existing
result readers and legacy KUMA results remain supported.

## Plug in a Judge

```powershell
agentbench evaluate AGENT_ID --sdk native --case-file cases.json --cases 1 --max-steps 2 --judge my_package:judge
```

The explicit module reference is trusted executable Python configuration. It is
never read from case contents. The module exports an object implementing
`agentbench.sdk.judges.Judge`:

```python
class MyJudge:
    def judge(self, request, *, directory, environ):
        # Read request['steps'] and hash-verified attachments beneath directory.
        # Call your own SDK/service here, using credentials from environ.
        return {
            'schema': 'abb.judge.result.v1',
            'request_id': request['request_id'],
            'status': 'inconclusive',
            'issues': [],
            'evidence_gaps': ['Implement the assessment method.'],
        }

judge = MyJudge()
```

`abb.judge.request.v1` contains the original case, run identity, ordered inputs
and results, unexecuted input IDs, and relative trace attachment paths with byte
sizes and SHA-256 hashes. Transport is adapter-owned: adapters may implement
local, SDK or HTTP judgments. ABB does not upload files merely by executing a
case. Hidden GT is not read into the request. Requests and responses are retained
under `evaluation/judge/`; the selected Judge runs on the host after execution
cleanup and trace validation. Delivery failures preserve Agent execution and
evidence. Received responses are reused when re-reading an attempt; ambiguous
or failed submissions are not automatically resent. This initial interface is
synchronous; provider-specific asynchronous polling/reconciliation belongs in
the adapter.

For an already saved request, Python callers can use `execute_judge(judge,
request, directory=attempt_directory, environ=...)` without invoking an Agent.
This writes assessment artifacts; it does not rewrite a completed Suite's event
history. A new assessment method must have a separate destination/task rather
than overwrite a previous assessment. The current CLI selects one Judge per run.

Use `--judge kuma` for the optional KUMA adapter. Only this selection requires
the KUMA host dependency and credentials. It translates original transported
spans into KUMA evidence and calls the official Judge provider, without generating
cases or executing the Agent again. KUMA requires homogeneous text or structured
inputs; mixed input cases remain executable with native ABB but are rejected by
this adapter. File snapshot/diff evidence is not supplied by this bridge and is
not represented as captured. Legacy KUMA execution retains its original file
capture and recovery workflow. Online service acceptance must be verified with
the deployed backend; offline translation tests do not establish it.

## Verification

`tests/test_native_cases.py` covers imports, multi-turn state, no-KUMA imports,
failure termination, saved-result state, Judge delivery and evidence integrity.
`tests/test_native_container.py` is opt-in with `ABB_NATIVE_TEST_IMAGE` pointing
to a local image with ABB's runtime dependencies and no KUMA installation. It
executes a deterministic stateful Agent in real containers and retains case,
output, spans and an independent Judge result under `results/verification/`.

## Complete independent local workflow

```powershell
agentbench evaluate react-agent --sdk local --case-file cases.json --cases 1 --max-steps 2
```

`local` now uses ABB's native executor and the `local` Judge protocol adapter.
Neither the host workflow nor its evaluation overlay requires KUMA. Without
`--case-file`, it calls the configured model with one generation prompt per case,
using the Agent Profile in `requirement.md` and its referenced input schema and
tool capabilities. It generates the whole conversation before execution (not
an adaptive next-turn loop). Generated inputs are validated for type, schema,
step budget and duplicate conversations. The frozen Profile travels with the
case so the Judge uses the same capability description. Generation requests and
responses are retained under the SDK output directory in `local-generation/`. For execution without a Judge,
use `--sdk native`. For native execution plus this same Judge, use `--judge local`.

The host Judge calls an OpenAI-compatible model directly. Configure
`ABB_LOCAL_JUDGE_BASE_URL`, `ABB_LOCAL_JUDGE_MODEL`, `ABB_LOCAL_JUDGE_API_KEY`,
or use the existing model-provider configuration. Local means locally controlled
assessment; the configured model endpoint may be remote and charge for tokens.
Credentials stay on the host. KUMA is never a fallback.

The provider assesses ordered inputs, outputs and transported trace contents.
It records its model, endpoint, prompt and raw reply beside the protocol result.
Execution/evidence failures are inconclusive rather than automatically labeled
Agent defects. Evidence larger than `ABB_LOCAL_JUDGE_MAX_CHARS` (default 120000 characters) is explicitly inconclusive,
not silently truncated. Findings are model assessments, not validated GT.

Historical local KUMA-worker modules are retained for legacy compatibility;
they are not used by new `--sdk local` runs. Old result files remain readable.

Local and KUMA use the shared `sdk.common.agent_context` loader and environment
snapshot assembler. The snapshot contains the original Profile, declared JSON
references, input type, Agent ID and a content hash. KUMA still uses its own
parser and converts environment facts into its supported Profile sections.
Local first runs a preparation-only container probe using the existing
`ExecutionEnvironment` / `observe_environment` interfaces, then generates on
the host. Credentials are not sent into the probe. The snapshot explicitly
labels these observations `sdk_controller`: they describe the preparation
controller, not all permissions or tools of the isolated target Agent. Local
passes the frozen snapshot to generation and Judge; KUMA saves it alongside
its existing generation Profile artifact. This does not reproduce KUMA strategies
or backend-specific repository metadata. Missing or invalid Profiles fail explicitly. Hidden
GT and upstream source files are not included in local model prompts.

The new context artifact is additive. Existing Case/result/report schemas are
unchanged; saved cases without this context remain readable and reusable.
Container probing does not invoke the target Agent. Reference-path checks are
shared, while evaluator-specific input/schema rules remain in each plugin.
