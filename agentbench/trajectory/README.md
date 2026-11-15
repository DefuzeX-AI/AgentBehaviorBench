# Trajectory evidence contract

`trajectory.json` is the step sequence of one Agent execution, derived once from
the raw records of an attempt directory and saved beside them. Schema
`abb.agent-trajectory.v1`. Every execute-phase result package carries one; a
generation failure still writes the file with `status: failed` and the error.

The raw records (`steps/NNNN/otel*.jsonl`, `framework.jsonl`, `logs/network.jsonl`,
ACP events, file evidence) remain the source of truth. The trajectory never
replaces them: `sources` lists the files it was derived from with digests, and
each step carries `evidence` identifiers that point back at the interaction index.

## Why this shape

The format follows the trace definition of TraceElephant (arXiv 2604.22708):
a flat sequence 𝒯 = ⟨s₁…s_T⟩ where each step records
`(input x_t, output y_t, acting component a(t), step_id, agent_id)` and tool
logs are attached to the step that issued the call. That paper's ablation shows
step-level attribution degrades most when per-step inputs or run metadata are
dropped, so both are stored complete. Compression happens only when rendering
for a reader (`render.py`), never in the stored file.

## Vocabulary

| Term | Meaning here |
| --- | --- |
| attempt | One execution of one Case: the directory `attempts/<id>/` (historical: `evaluation/inputs/` inside it). |
| SDK Input | One prompt the SDK sent to the Agent: `steps/NNNN/`. Trajectory steps reference it as `input_ordinal`. |
| step | One Agent action in the paper's sense: a model call with the tool executions it emitted, or a tool execution no model call emitted (`kind: tool_only`). |
| tool log | One tool execution: arguments, outputs, execution status, terminal exit status when ACP observed one. |

Framework chain and middleware spans (LangGraph nodes, DeerFlow middleware)
are not steps. They stay in the raw evidence and are reachable through
`evidence.framework_span_id`.

## Fields

```jsonc
{
  "schema": "abb.agent-trajectory.v1", "builder_version": 4,
  "status": "complete" | "partial" | "failed",
  "run_id", "agent_id", "case_id", "framework",
  "metadata": {
    "task_instruction",                          // first Case input, complete
    "agent_configuration": {"agents": [{"agent_name"}], "system_prompt", "tools", "runtime"},
    "system_architecture": {"framework", "source_revision", "profile": {"path", "sha256"}, "binding": {...}}
  },
  "steps": [{
    "step_id": 1, "input_ordinal": "0001", "agent_name", "kind": "model" | "tool_only",
    "source": "wire" | "wire+framework" | "framework", "started_at", "ended_at",
    "model", "purpose", "status",
    "input": {"messages", "system"?, "tools"?, "model"?, "parameters"?},   // the request the model received
    "output": {"text", "reasoning", "tool_calls": [{"id", "name", "arguments"}], "finish_reason", "usage", "model"},
    "tool_logs": [{"tool_call_id", "tool_name", "input_arguments", "outputs",
                   "execution_status": "succeeded" | "error" | "not_observed",
                   "exit_status": {"exitCode", "signal"} | null,
                   "link": "exact" | "ambiguous" | "none", "evidence": {...}}],
    "evidence": {"interaction_id", "call_id", "framework_span_id", "request_sha256", "response_sha256"}
  }],
  "inputs": [{"ordinal", "input_id", "prompt", "step_range": [first, last], "result": {...}, "file_changes": [...]}],
  "coverage": {"model_calls", "tool_calls", "file_changes", "ambiguous_links", "unlinked_tool_calls", "unobserved_tool_executions"},
  "sources": [{"path", "sha256"}], "warnings": []
}
```

`output.wire_error` is present when the interceptor recorded a transport failure;
`output_source: framework` then marks that the output came from the framework
span instead. `output.tool_calls_source: graph_node` marks tool calls recovered
from the enclosing LangGraph node when a streamed generation kept none.

Strings larger than `ABB_TRAJECTORY_MAX_VALUE_BYTES` (default 1 MiB) are
replaced by `{"truncated": true, "size", "sha256", "head"}`.

## Pairing rules

Relationships come from recorded identifiers only; timestamps order steps.

- Interceptor records group by `call_id`; framework records group by span id.
- A wire model call joins its framework model span through the
  `framework_span_id` header when their recorded invocation identities are compatible.
  Both sides of that pair form one step; conflicting identities remain separate.
- Tool executions join the model call whose output emitted their
  `tool_call_id` through the shared resolver in `observe/tool_links.py`. Recorded
  run, Case, attempt, Input, invocation and native-session identities must not
  conflict. Missing identity is unknown, never evidence of a match. Exactly one
  execution candidate and one possible emitting model is `exact`; multiple
  candidates or owners are `ambiguous`; none is `unobserved` in the interaction
  relation (`not_observed` in the trajectory tool log). Unresolved executions
  remain complete `tool_only` steps; no candidate is selected arbitrarily.
- Input identity also comes from `request.json.observation_context` when absent
  in `input.json`. Contradictions are recorded as `identity_conflicts` and block
  exact associations. A tool ID recorded only on span end remains usable.
- LangGraph: the acting component comes from `langgraph_checkpoint_ns` of the
  model span (`agent/subgraph` for nested graphs). ACP: the Agent identity.
- ACP agents expose no internal model spans; their model calls are the wire
  records, their tool logs the ACP `tool_call` updates, with terminal
  `exitStatus` when the client observed the terminal.

## Builder stages

`builder.build(directory)` reads the attempt through `RunViewAPI` and the
cached `InteractionIndex`, so current `steps/` and historical
`evaluation/inputs/` layouts resolve the same way.

1. `sources.py` selects wire model calls, framework model spans and tool rows.
2. `content.py` turns request/response bodies into complete `input`/`output`
   values (merging streamed chunks) and extracts terminal exit status.
3. `actors.py` names the acting component.
4. `files.py` attaches committed file diffs, or replay deltas, to each Input.
5. `metadata.py` assembles task, configuration and architecture references
   from the Case, the first model request and the registered Agent unit.
6. `schema.validate` checks the result before it is saved.

`write(directory)` is called by `sdk/integration/execution.py` after both
containers stop and host trace validation ran, before SDK diagnostics collect
the package. `observe/service.py` does the same for observe runs.
`agentbench trajectory build DIR --write` derives the file for historical
attempts, including ground-truth references.

## Consumers

- `agentbench trajectory show DIR` and `render.py`: `full`, `truncate_middle`
  (requests over 3000 characters keep head and tail) and `response_only`.
- Native Judge requests attach `trajectory.json` (`sdk/judges.py`). KUMA uses
  its committed SDK evidence and does not upload or require the derived file;
  old queued tasks ignore their legacy trajectory hash entry.
- `EvaluationService.evidence()` returns it under `trajectory`, raw spans under
  `spans`; the viewer route `trajectory` serves it.
- Ground-truth matching compares reference and candidate trajectories by step.

Builder version 2 retains the `abb.agent-trajectory.v1` schema. It also reconstructs
Responses text, reasoning summaries and function arguments from recorded stream
fragments without requiring a final response body. Final item events replace their
partial content rather than duplicating it. Only recorded content is rendered.
Saved trajectories are not silently rebuilt; use the explicit build command to
regenerate an older derivation from its raw evidence.

### Standalone observe inputs (builder version 3)

The reader resolves standalone requests at `invocation-*/input/request.json`
while keeping framework logs and results under `invocation-*/output/`.
`steps/NNNN` and historical `evaluation/inputs/NNNN` remain supported.
An existing `input.json` remains authoritative; otherwise the standalone request's
`input` is the prompt and `framework` supplies the framework identity. The request
is included in source hashes. Neither files nor Agent input/output are rewritten.

Standalone invocation folders have distinct ordinals, so multiple calls cannot
collapse into one `output` Input. The recorded invocation ID scopes associations;
a benchmark `input_id` is only populated when it was actually recorded. Missing
requests and contradictory identities remain incomplete evidence. Readers retain
the artifact API's path-boundary and symlink checks.

### Interrupted model streams (builder version 4)

Replacement-mode SSE capture emits `llm_delta` with the same native payload,
call and framework-span identifiers, sequence number and elapsed time as the
desktop App. Each complete SSE frame is persisted as it arrives, with existing
secret redaction, independently of stream completion. `llm_chunk` remains a
transport metric; it does not contain text. Forwarding and model conversion are
unchanged. Unary and non-SSE traffic retain their existing collection paths.

The builder continues to prefer `llm_response`, then an available completed
framework output. If neither exists, it reconstructs only recorded `llm_delta`
payloads for that call, ordered and deduplicated by sequence. Existing protocol
decoders preserve text, reasoning and tool arguments, including unfinished
arguments. No tool execution, finish reason or final usage is invented.

Such steps carry `output_source: wire_delta`, a stream event count and digest
in `evidence`, and a warning that makes the trajectory `partial`. Recorded model
errors and their timestamps remain present; a stream without a terminal record
is `incomplete`, not successful. The execution's own outcome is never changed.
A completed response supersedes stream fragments rather than duplicating text.
Older runs with only chunk metrics cannot recover text that was never recorded.
