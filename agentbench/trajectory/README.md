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
  "schema": "abb.agent-trajectory.v1", "builder_version": 1,
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
  `framework_span_id` header. Both sides of that pair form one step.
- Tool executions join the model call whose output emitted their
  `tool_call_id` (`observe/tool_links.py`). One candidate in the same Input
  is `exact`; several are `ambiguous`; none means the execution was
  `not_observed`. A tool execution no model call emitted becomes a
  `tool_only` step.
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
