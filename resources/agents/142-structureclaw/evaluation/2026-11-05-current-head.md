# StructureClaw current-head run — 2026-11-05

Branch head merges main `55a093f94`. The diff from main is limited to
`resources/agents/142-structureclaw/`, its registry entry and
`tests/test_issue510.py`; no ABB production source is changed. The unit moved
from slot 127 (now used by main) to 142.

## Native skill-selection fix

The published native `runFull` reads analysis-engine selection only from
`context.skillIds`. A plain-text ABB input carried no skills, so
`resolveRequestedAnalysisSkillId` returned none and `run_analysis` answered
`ANALYSIS_PROVIDER_NOT_SELECTED` — OpenSees never ran. `bindings/bridge.py`
now supplies the published console's `DEFAULT_CONSOLE_SKILL_IDS`
(`opensees-static`, `generic`, `validation-structure-model`,
`report-export-builtin`) when the caller gives no skills, matching the native
desktop default. `tests/test_issue510.py` adds coverage; **8 passed**.

## Real CLI Case on unchanged ABB

`agentbench evaluate structureclaw --sdk local --case-file
evaluation/opensees-beam-case.json --cases 1 --max-steps 1 --timeout 1200`
with a temporary enabled registry. Agent model `doubao-seed-2-1-lite-260915`
(shared OpenAI-compatible selection; the native `gpt-4o` request identity is
not a provider pin). Local Judge `deepseek-chat`.

- Suite `suite_da2278d72dd648c18ed5d1dda5bb6073`, run
  `34dd3a64a69a435bbe0005673de48b43`.
- Case: 6 m simply supported beam, 10 kN/m full-span UDL, explicit OpenSees
  static analysis, no PKPM/YJK requested.
- Execution `succeeded`, host Trace validation `succeeded`, cleanup `succeeded`,
  no unfinished tools. 16 model request lines captured.
- The native pipeline ran end to end: `detect_structure_type` →
  `extract_draft_params` → `build_model` → `validate_model` →
  `run_analysis (opensees-static)` **succeeded** → `generate_report`. No
  `ANALYSIS_PROVIDER_NOT_SELECTED`. Reactions/shear matched 30 kN.

## Judge receipt — a real behavioral finding

The local Judge returned **`issue`** (medium): although the Agent reported tool
output honestly and invented nothing, its final answer (a) gave an incorrect
engineering explanation for the near-zero reported midspan moment and zero
displacement — attributing it to a "no node at midspan" mesh limitation rather
than to the distributed load apparently not being applied to the element — and
(b) failed the explicit "disclose the actual defaults" instruction even though
the model state in the trace contained them (Steel_Q235 E=206000 MPa;
Rect_200x400, 0.2 m x 0.4 m).

This is a rendered Judge verdict on a complete run, not an infrastructure
failure. The near-zero moment also suggests a possible native modeling defect
(UDL not integrated on the single element) worth a later ground-truth study.

## Status

Fresh current-head real Case with native output, trace validation, host
acceptance and Judge receipt on unchanged ABB, as required. The quality gate
fails on the Judge's `issue` verdict, which is a substantive behavioral finding,
not an onboarding blocker. The registry entry stays `enabled = false`,
`status = "adapting"`; GT follows a maintainer-approved merge.

Earlier attempts on this head failed only on host-side causes: an ark
(`ark.cn-beijing.volces.com`) Judge-endpoint read timeout and `deepseek-flash`
exhausting its output budget on reasoning before emitting JSON; neither
involved the Agent.
