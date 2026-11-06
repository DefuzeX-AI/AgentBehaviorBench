# Audit of the 2026-11-05 Judge finding — 2026-11-06

Reply to the 2026-11-06 review. The failing receipt stays on record unchanged:
[2026-11-05 notes](2026-11-05-current-head.md) and the verbatim
[Judge report](2026-11-05-judge-report.json) (`issue`/medium, suite
`suite_da2278d72dd648c18ed5d1dda5bb6073`, run
`34dd3a64a69a435bbe0005673de48b43`). No bridge, Case, Judge or ABB source change
is made here, and no new Agent run was needed: the analysis is deterministic and
is reproduced below without an LLM.

## Summary

| Judge statement | Assessment |
|---|---|
| (a) ~0 moment means the UDL was not applied to the element; the answer's "no midspan node" explanation is wrong | **Mechanism wrong.** The load was applied to the element. Zero end moments are correct for one pinned–roller element, and the 45 kN m peak is not sampled because there is no interior node. The Agent's explanation was right. |
| (b) answer omits defaults that are in the trace state | **The Agent could not see them.** No tool output showed the defaults to the model. The Judge's own `evidence_gaps` says so. |
| Overall `issue` | **Correct outcome, wrong reason.** The run is still wrong: the native generic draft applied 10,000 kN/m, not 10 kN/m. The answer's "30,000 → 30 kN" conversion assumes N units that the engine does not use. |

The `issue` verdict should stand. Both defects are in the published
StructureClaw 1.1.0 code. The unit cannot fix them without patching upstream
code, using a canned answer or changing the Case.

## Trace references

Paths below are relative to the retained results directory
`agents/structureclaw/cases/99ebe30cfbad57c9995da6defcc44a0a/attempts/34dd3a64a69a435bbe0005673de48b43/`.
JSON paths are in `steps/0001/result.json`.

- `raw_output.state.messages[5]` (build_model) contains only `{"success":true,"nodeCount":2,"elementCount":1,...}`.
- `raw_output.state.messages[7]` (validate_model) contains only counts (`materials:1, sections:1`).
- `raw_output.state.messages[9]` (run_analysis) contains only `keyMetrics`:
  `maxAbsShearForce 30000`, `maxAbsMoment 3.64e-12`, `maxAbsDisplacement 0`,
  `maxAbsReaction 30000`. No units are given.
- `raw_output.state.messages[12]` is the final answer. Its explanation is "no node at midspan", and it states "the tools did not expose the actual section dimensions or material modulus".
- `raw_output.state.model` contains: 2 nodes; `restraints` N1 `[T,T,T,F,F,F]`, N2 `[F,T,T,F,F,F]`; one element `E1`; `load_cases[0].loads[0]` = `{"type":"distributed","element":"E1","wz":-10000}`; `Steel_Q235 E=206000`; `Rect_200x400 Iy=2.67e-4, Iz=1.07e-3`.
- `raw_output.state.analysisResult.data`: `forces.E1.n1/n2` V = 30000, M = ±3.6e-12; `displacements.N1.ry` = −1.6363041343951128, `N2.ry` = +1.6363041343951128 rad. The Agent never received these values.
- `judge/report.json` `evidence_gaps[1]`: "No tool output explicitly listing section/material defaults was returned to the Agent."

## Engine units (published source)

`backend/src/agent-skills/analysis/opensees-static/opensees_static_analysis.py`:

- In `_define_beam_element_2d` (lines 241–259), the element modulus is `material.E * 1000` and the bending inertia is `Iy`. E is entered in MPa and becomes kN/m², so the engine works in **kN and m**.
- Lines 31–34: a 1D beam is solved in the `xz` plane. Its fixed DOFs come from `restraints[0], [2], [4]` (ux, uz, ry).
- `-beamUniform` passes `wz` unchanged, so `wz` is in kN/m.

## Hand calculation (L = 6 m, w = 10 kN/m, pinned–roller)

- R = V_end = wL/2 = **30 kN**. M(x) = wx(L−x)/2, so M(0) = M(L) = **0** and M(3) = wL²/8 = **45 kN m**.
- The model's EI = 206000×1000 kN/m² × 2.67e-4 m⁴ = 55,002 kN m².
- End rotation θ = wL³/(24EI). For w = 10 kN/m, θ = 2160/(24×55,002) = **1.636e-3 rad**. The run reports **1.636 rad**, exactly 1000× larger. So the engine used w = 10,000 kN/m, the drafted `wz=-10000`. In engine units the reported shear and reactions of 30000 are **30,000 kN**.
- A one-element model reports element-end forces only, so the 45 kN m midspan value cannot appear. The support translations are restrained, so `maxAbsDisplacement` = 0 is also expected. Element-end V = 30000 with zero end moments is the response to a load applied *on the element*. If the load had been applied as nodal loads at the supports, it would go straight into the reactions and the element shear would be 0.

The `wz=-10000` value comes from the native generic skill's model template. In
`backend/src/agent-skills/structure-type/generic/llm-model-prompt-fragments.ts`
lines 20–23, the template shows `fz: -10` next to `wz: -10000`. The Agent's model
copied it, and also copied the template's example material and section
(`Steel_Q235`, `Rect_200x400`). Those values are what the Judge called "the
actual defaults".

## Native reproduction without an LLM

[`native-probe/run.sh`](native-probe/run.sh) runs the package's own OpenSees
worker in the unit image (`sha256:b7634b54b00b…`, StructureClaw 1.1.0, openseespy
3.7.1, `--network none`). The output is in [`native-probe/output.txt`](native-probe/output.txt).

| Model | Midspan M | Support M | Shear/reaction | Displacement |
|---|---|---|---|---|
| Run model, unchanged ([json](native-probe/run-34dd3a64-model.json)) | no node | 3.6e-12 | 30000 | ry = ±1.6363 rad (same bits as the run) |
| Same model, `wz=-10` ([json](native-probe/control-run-model-load-kN.json)) | no node | 0 | 30 | ry = ±1.636e-3 rad = wL³/24EI |
| Same model, `wz=-10`, midspan node ([json](native-probe/control-run-model-load-kN-midspan-node.json)) | **45.0** | 0 | 30 | uz = −3.068 mm = 5wL⁴/384EI |
| Native **beam** template (`buildLegacyModel`, same draft) | 15.0 | **30.0** | 30 | uz = −1.646 mm = wL⁴/384EI |

The engine is correct when it is given a correct model (row 3). The run model
alone reproduces the run bit for bit (row 1).

## Why the unit cannot fix this

- **Generic skill** (the console default and the current route): whether the LLM copies the `wz` scale from the template is not something the unit controls.
- **Native beam skill** (selectable by adding `beam` to `skillIds`): this route is worse. `model-builder.js` `buildBeamNodes` releases only `restraints[5]` (rz) for pinned and roller supports, but the solver bends the beam about `ry` (`restraints[4]`). A "simply supported" beam is therefore solved as fixed-fixed (row 4: support M = wL²/12 = 30, midspan M = wL²/24 = 15). The Agent would report the wrong maximum moment with full confidence. The 10-26 run selected this template, but its solve never succeeded, so the defect did not show then.
- **Defaults disclosure**: `build_model` returns counts only by design (`dist/backend/agent-langgraph/tools.js` `buildModelToolSummary`, lines 401–423). No native tool returns the material or section to the model.

Selecting another skill set, or feeding the model to the Agent from the bridge,
would either produce a wrong solve or replace native behavior. The registry entry
stays `enabled = false`, `status = "adapting"`. Both defects should be reported
upstream: the generic template's unit scale, and the beam template's pinned
restraint vector for the `xz` solve.
