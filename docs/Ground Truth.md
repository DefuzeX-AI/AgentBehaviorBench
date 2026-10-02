# Ground truth and discovery assessments

[Guide](Guide.md) · [简体中文](otherLanguages/Ground%20Truth.zh-CN.md)

Ground truth records a real Agent defect that a person has confirmed through repeated execution of the same Case. Benchmark Overview reports whether generated Cases reproduce those defects and whether Judge reports identify them correctly. These are host-owned reference and assessment interfaces; there is no automatic quality evaluator or defect matcher yet.

## Retain confirmed defects

Keep the reference directory beside `agent.toml`, outside the upstream `agent/` source:

```text
resources/agents/03-react-agent/
  agent.toml
  agent/
  ground_truth/
    manifest.json
    observations/defect-1/
      case.json
      run-1.zip
      run-2.zip
```

Preserve every round's original Case, inputs, Agent outputs, traces, Judge report, execution configuration, and human notes in this directory. An observation's evidence file can be an archive containing its full capture. Use actual execution identities as observation IDs and retain the Suite/Attempt identities inside each capture. A reference requires at least two distinct observations of the **same Case**, followed by human confirmation. Supplying two IDs alone does not establish reproducibility; the reviewer remains responsible for the evidence's meaning.

Illustrative manifest; replace all angle-bracket placeholders with real values. Hashes are 64 lowercase hexadecimal characters.

```json
{
  "schema": "abb.agent.ground_truth.v1",
  "agent_id": "react-agent",
  "defects": [{
    "id": "defect-1",
    "title": "<short defect title>",
    "expected_behavior": "<required behavior>",
    "observed_behavior": "<human-confirmed defect>",
    "confirmed_by": "<reviewer>",
    "confirmed_at": "2026-10-02T12:00:00Z",
    "source_sha256": "<Agent execution source hash>",
    "case_sha256": "<reference Case file hash>",
    "observations": [
      {"id": "<first execution ID>", "case_sha256": "<same reference Case file hash>",
       "evidence_path": "observations/defect-1/run-1.zip", "evidence_sha256": "<first archive hash>"},
      {"id": "<second execution ID>", "case_sha256": "<same reference Case file hash>",
       "evidence_path": "observations/defect-1/run-2.zip", "evidence_sha256": "<second archive hash>"}
    ]
  }]
}
```

- `source_sha256` is the Agent's saved `plan.json` registration hash for the executions being confirmed. For a new reference, `agentbench.harness.session.plan.source_digest(unit)` computes the current execution-source hash. Do not assign a current hash to observations made against different code.
- `case_sha256` and `evidence_sha256` hash exact file bytes with the exported `file_digest(path)`. Case hashes use the retained artifact, not the SDK's semantic `content_sha256`.
- Evidence paths are relative to `ground_truth/` and must remain inside it. Keep complete observations independently of disposable result directories.
- `load_manifest(unit, agent_id)` validates declarations and evidence hashes, then adds each defect's `ground_truth_sha256 = digest_json(raw_defect_record)`. Editing that record changes its revision and invalidates assessments bound to its previous hash.
- Ground truth files do not affect execution-source provenance and are excluded from ABB worker/SDK staging copies. Newly generated `.dockerignore` files exclude `/ground_truth/`; add that rule to existing units before direct or manual Docker builds. The upstream source's own nested `agent/ground_truth/` remains ordinary source. Do not add reference answers to `requirement.md`.

## Assess one saved Attempt

Write explicit decisions to `<Suite directory>/ground_truth/assessments.json`. A generated Case may differ from the reference reproducer; a reviewer decides whether it exposes the **same defect**. Its `case_sha256` must bind its own retained Case artifact.

| Field | Meaning |
| --- | --- |
| `case_reproduced` | `true`: this Case exposed the referenced defect; `false`: it did not; `null`: not assessed. |
| `judge_detected` | `true`: the saved Judge report correctly identified that reproduced defect; `false`: it did not; `null`: not assessed. |
| `ground_truth_sha256` | Exact reference-defect revision returned by `load_manifest`. |
| `result_sha256` | `digest_json` of the complete saved Attempt result, including its Judge report. |

`judge_detected: true` requires `case_reproduced: true`. A reproduced defect with `judge_detected: false` records a Judge miss. Execution completion or an `issue` verdict alone supplies neither decision. Positive and negative decisions require a completed execution; a Judge decision also requires a saved report. Rejected or invalid evidence cannot contribute a valid assessment.

The following developer example prints a validated sidecar document. Replace the paths, IDs, review text and decisions after inspecting the evidence. It uses existing artifacts and makes no Agent or SDK calls.

```python
import json
from pathlib import Path
from agentbench.harness.ground_truth import (
    ASSESSMENTS_SCHEMA, digest_json, load_manifest, validate_assessment,
)
from agentbench.harness.session.store import read_suite
from agentbench.harness.session.snapshot import suite_snapshot

unit = Path("resources/agents/03-react-agent").resolve()
suite = Path("results/suites/<suite-id>").resolve()
agent_id, defect_id, case_index, attempt_id = "react-agent", "defect-1", 0, "<attempt-id>"
plan, events = read_suite(suite)
snapshot = suite_snapshot(plan, events)
job = next(job for job in snapshot["jobs"] if job["agent_id"] == agent_id)
case = next(case for case in job["cases"] if case["case_index"] == case_index)
attempt = next(item for item in case["attempts"] if item["attempt_id"] == attempt_id)
defect = next(item for item in load_manifest(unit, agent_id) if item["id"] == defect_id)
assessment = {
    "agent_id": agent_id, "case_index": case_index, "attempt_id": attempt_id,
    "ground_truth_id": defect_id, "ground_truth_sha256": defect["ground_truth_sha256"],
    "case_sha256": case["prepared_case"]["artifact_sha256"],
    "result_sha256": digest_json(attempt["result"]),
    "case_reproduced": True, "judge_detected": False,
    "reviewed_by": "<reviewer>", "reviewed_at": "2026-10-02T12:00:00Z",
    "rationale": "<specific observed behavior and corresponding Judge finding or omission>",
}
validate_assessment(assessment, {"plan": plan, "snapshot": snapshot, "directory": suite},
                    {(agent_id, defect_id): defect})
print(json.dumps({"schema": ASSESSMENTS_SCHEMA, "suite_id": plan["suite_id"],
                  "assessments": [assessment]}, indent=2))
```

For an existing sidecar, preserve its other assessments and add the new record. Publish the complete JSON file atomically. Identical duplicate records count once; conflicting decisions for the same Agent, Case slot, Attempt and defect are rejected. The loader checks the Suite identity, Agent source hash, retained Case bytes, exact Attempt result and reference revision. These checks validate association and integrity, not the factual correctness of the human judgment.

## Overview semantics

- Discovery is counted once per Agent and current reference defect across all accepted saved Suites. Reuse and retries add evidence; they do not multiply known or discovered defects. A later retry does not erase an earlier valid discovery.
- A defect is fully assessed when an accepted record contains both decisions. Partial assessments remain visible. Any accepted `true` establishes historical reproduction/discovery; otherwise explicit `false` is retained, with `null` when there is no decision.
- `discovery_rate` uses all valid known defects as its denominator. It remains `null` until at least one defect is fully assessed; unknown or unconfigured data is never presented as 0%.
- Missing manifest: `not_configured`; empty manifest: `empty`; no decisions: `not_assessed`; partial coverage: `partially_assessed`; every defect fully assessed: `assessed`. Invalid definitions or associations produce warnings and are excluded from valid outcomes.
- `GET /api/benchmark/overview` is read-only. It rereads reference/assessment changes without requiring a new Suite event. Legacy Suites without canonical provenance retain execution counts but cannot supply validated GT assessments.

JSON documents are limited to 2 MiB and referenced evidence files to 64 MiB each. This interface does not generate Cases, invoke Judge, collect missing observations, or automatically establish Case-generation quality, Judge accuracy, or false-positive rates.
