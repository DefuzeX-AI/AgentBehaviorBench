# Execution Flow UI Prototype

Question to resolve: which view makes a real run easiest to understand—the flow map, sequence lanes, or focused reading?

Start the prototype by running `npm run dev -- --port 5174` in `web/`, then open
`http://127.0.0.1:5174/?variant=A#view=flow`. Switch between A, B, and C from the floating toolbar or the selector at the top.
The page uses the current Run's read-only APIs and refreshes snapshots manually. The existing timeline remains available.

- A: a spatial map of Case/Input, root Agent calls, and results/evaluation; expanding a child call collapses single-branch framework wrappers that contain no interactions.
- B: a downward time sequence with SDK, Agent, LLM, and Tools lanes; complete calls are grouped together.
- C: three columns for call navigation, current content, and direct child calls; follow a path one level at a time to inspect input and output.

Solid edges come from parent-child relationships within the same trace. Dashed edges represent Input or framework-span links; select an edge to inspect its evidence.
Unlinked calls remain separate. Matching tool names, nearby timestamps, or tool requests returned by a model are not treated as execution evidence.
Global SDK/Judge snapshots remain viewable, but the prototype does not add flow edges when they have no Input ID.

New Agents and SDKs may provide an optional `observation_context` in `abb.invocation.v1`:
`{ "case_id": "...", "input_id": "..." }`. This does not change the `input` sent to the Agent.
The worker writes these two IDs, the actual invocation_id, and agent_id into framework JSONL records and the result.
OTel spans store `abb.case_id`, `abb.input_id`, and `abb.agent_id`.
The KUMA adapter populates these fields from the SDK's raw Input snapshot; other SDKs can use the same convention.
Existing parent_span_id values and start/end events remain the evidence for calls and timing. Older records are not backfilled with new fields.

Record the selected design after review: ____. Once selected, refine the winning layout into the production page and remove the other prototype layouts.
