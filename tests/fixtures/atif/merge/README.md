# Recorded runs for the ATIF merge

Seven `agentbench chat openclaw` runs (OpenClaw 2026.9.5), cut down to what the
`acp_otel` step source reads. `tests/test_atif_merge_runs.py` merges each one
and compares the result with `expected.json`.

| Directory | What the run recorded |
| --- | --- |
| `two_text_turns` | Two prompts answered with text only. No span names its turn. |
| `parallel_tool_calls` | Two turns; one model call emits two tool calls. |
| `nine_model_calls` | One turn with nine model calls and their tools. |
| `one_child_two_turns` | One spawned child that still runs when the second prompt arrives. |
| `delayed_second_prompt` | The Agent starts the second prompt seven seconds after it was sent. |
| `lost_model_call` | The export stopped early: one model call and one tool exist only on the wire and in ACP. |
| `parallel_children_lost_turn` | Two children spawned by one call; the trace has nothing of the second turn. |

## What was cut

`trim_run.py <run directory> <new fixture directory>` made each directory. The
rows keep their recorded identifiers, timestamps and order.

- `otel/spans.jsonl`: every span. Tool definitions and system instructions are
  dropped, input messages keep only the replayed tool call ids, and long tool
  results are shortened.
- `logs/network.jsonl`: the request and response of each model call. The
  request body is emptied; the streamed response is stored as one
  non-streaming response with the same text, tool calls and usage.
- `steps/NNNN/acp-events.jsonl`: prompt boundaries, tool call reports and
  reply text. Long tool output is shortened.
- `run.json`, `request/target.json`, `acp-summary.json`: only the fields the
  reader uses.

## expected.json

The outline the test compares: per step its source, the first characters of
its message, `extra.abb.sources`, `owner` and `kind` when present, and each
tool call with the sources of its execution. Each outline was checked against
the full run it was cut from before it was stored. When a rule changes, review
the new outline before replacing the file.
