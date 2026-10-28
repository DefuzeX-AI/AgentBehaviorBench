# Shared evaluation service

For Issue-level detection from an imported Case directory, see
[Experiment 1](Experiment1.md). Its `exp1` command reuses this execution service
and assesses trajectories directly without a Judge report.

`agentbench.evaluation.EvaluationService` owns the application operations used by
Python and `agentbench api`. The CLI parses arguments and emits JSON; it does not
implement another executor, Judge protocol, or GT matcher. MCP is not included.

The service reuses the native SDK, Suite scheduler, durable Case/artifact store,
Judge protocol and GT evaluator. Existing interactive commands use the same runner
configuration and scheduler boundary. Their prompts and viewer remain CLI-owned.

## Python workflow

```python
from agentbench.evaluation import EvaluationService

service = EvaluationService(project_root, environ=host_environment)
info = service.agent("my-agent")
execution = service.execute("my-agent", [
    {"case_id": "check-1", "inputs": [{"input_id": "step-1", "payload": "Hello"}]}
], results_dir=output_root)
suite = execution["directory"]
run_id = execution["runs"][0]["id"]
evidence = service.evidence(suite, run_id)
request = evidence["request"]
for path in request["attachments"]:
    content = service.attachment(suite, run_id, path)

# The testing Agent analyzes evidence and supplies its own report.
response = {
    "schema": "abb.judge.result.v1",
    "request_id": request["request_id"],
    "status": "pass",
    "confidence": "medium",
    "reason": "No violation established in this Case.",
    "issues": [],
    "evidence_gaps": [],
}
service.submit_judge(suite, run_id, response)
gt = service.evaluate_gt(suite)
final = service.result(suite)
```

The example verdict illustrates the schema; callers must derive the verdict from
evidence. `issue` requires findings containing an executed `input_id` and a
nonempty `message`. `inconclusive` requires evidence gaps. `pass` cannot contain
findings or gaps. The request ID binds a report to its Case and evidence hashes.

`execute` blocks until execution and cleanup finish. Omit `judge` to collect
evidence for an external testing Agent; pass `judge="local"` to use the configured
host Judge. Explicit trusted `module:object` adapters remain supported. Report
submission cannot replace an assigned Judge or overwrite an existing different
report. Identical submissions are idempotent. Failed provider delivery still
requires the existing reconciliation workflow; it is not silently retried.

The service accepts a fixed Case collection; adaptive turn generation and live
MCP sessions are outside this interface. Each execution creates a new Suite.
Agent Profile/reference content is snapshotted into submitted Cases. Public
Agent information omits ground truth and credentials. GT is accessed only by
the final evaluator, after the testing Agent has committed its findings.

## CLI workflow

```bash
agentbench api agent my-agent
agentbench api execute my-agent --case-file cases.json --results-dir results
agentbench api result --suite SUITE_DIRECTORY
agentbench api evidence --suite SUITE_DIRECTORY --run-id RUN_ID
agentbench api attachment --suite SUITE_DIRECTORY --run-id RUN_ID --path evaluation/inputs/0001/spans.jsonl
agentbench api submit-judge --suite SUITE_DIRECTORY --run-id RUN_ID --report report.json
agentbench api gt --suite SUITE_DIRECTORY
```

The Case file uses `{"schema":"abb.cases.v1","cases":[...]}`. Optional global
`--root PROJECT` and `--env-file FILE` precede the operation. The environment file
is loaded only by the CLI; Python callers supply their environment explicitly.
Use a short absolute `--results-dir` on Windows to leave room for Suite/Attempt
artifact paths on hosts without long-path support.

Successful API calls emit one JSON object on stdout; progress goes to stderr.
Exit code zero means the operation returned a response, not that the Agent passed
or GT matched. Inspect execution, Judge, and GT statuses in the response. Errors
emit `{"error":{"type":"...","message":"..."}}` and exit nonzero.

## Results and evidence

`result` returns `abb.evaluation.result.v1`, the Suite snapshot, its canonical
directory, and execution Run identities (preparation runs are excluded).
Execution status, host acceptance, evidence status, Judge delivery/status and
quality gate remain distinct. `suite.gt_evaluation` contains the latest GT
assessment when one exists. External reports update the original Attempt and
refresh Suite aggregates without re-executing the Agent or deleting history.

`evidence` returns the retained Judge request, trajectory index and evaluation
inputs/outputs. Attachments include execution payloads and file evidence, with
byte sizes and SHA-256 hashes. `attachment` returns the requested UTF-8 file in
full and rejects paths outside the registered attachment set. Binary artifacts
remain available in the local artifact directory; this text interface does not
decode them. Evidence is hash-validated before reads and Judge submission.

GT assessment is explicit so external clients can submit all reports first. It
reuses the two-stage evaluator: execution reproduction, then report recognition.
No GT, source mismatch, incomplete evidence, unknown decisions and provisional
review status retain their existing meanings. Reassessing GT does not rerun the
target Agent. A report submission changes Suite events, making older GT results
stale until reassessment.

## Validation

`tests/test_evaluation_service.py` exercises scheduling, persisted results,
external report submission, CLI/Python parity and two-stage GT integration with
an injected matcher. `tests/test_evaluation_service_container.py` is opt-in via
`ABB_NATIVE_TEST_IMAGE`; it uses an existing no-KUMA image and retains real
execution artifacts. Its synthetic GT matcher tests the protocol, not model
quality. Set `ABB_SERVICE_TEST_ROOT` to a short output root on Windows.
