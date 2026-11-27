# Trajectory

`trajectory.atif.json` is the trajectory of one attempt: an
[ATIF-v1.8](https://docs.harborframework.com/agents/atif) document derived from
the raw records of the attempt directory and saved beside them. It is the only
trajectory ABB writes; the earlier `trajectory.json` (`abb.agent-trajectory.v1`)
is no longer produced or read.

The raw records (`steps/NNNN/framework.jsonl`, `steps/NNNN/acp-events.jsonl`,
`logs/network.jsonl`, `otel/spans.jsonl`, file evidence) remain the source of
truth. The document holds the official ATIF steps and, under `extra.abb`,
pointers into those records instead of copies of them.

## When it is written

`sdk/integration/execution.py` and `observe/service.py` call
`atif.attempt.write` after the container stops and host trace validation ran.
The status is recorded as `atif` in `run.json`: `complete`, `partial`,
`failed` or `unavailable` (Harbor not installed). None of these changes the
execution outcome. Native Judge requests attach the file (`sdk/judges.py`).

## Pipeline

| Module | Responsibility |
| --- | --- |
| `atif/reader.py` | Reads what every source shares: Inputs, ACP events, raw records and Agent-exported OTel. |
| `atif/sources/` | Step sources chosen by a factory: `langgraph` takes model and tool steps from callbacks, `acp_otel` from the spans an ACP Agent exported. A special format adds a module here. |
| `atif/hierarchy.py`, `atif/adapters/` | Resolves the root execution and explicitly declared delegation adapters. |
| `atif/assembler.py`, `atif/replies.py` | Builds official Harbor `Step` objects and places them in turns. |
| `atif/validation.py` | Validates the complete document: schema, record conservation, ownership. |
| `atif/slim.py` | Reduces the validated document to the stored form and checks every pointer. |
| `atif/attempt.py` | Run-flow entry point; saves the file and returns the `run.json` status. |
| `content.py`, `sources.py` | Normalize provider and framework payloads; select calls from the interaction index. |
| `agent_otel.py` | Reads Agent-exported spans and turns inference spans into model records. |
| `metadata.py` | `capture_target` freezes the Agent unit into `request/target.json`. |

Records are paired by recorded identifiers only (interceptor call id, framework
span id, emitted tool call id); timestamps never create relationships. Grouping
and pairing reuse `observe/interactions.py` and `observe/tool_links.py`.

See [Automatic derivation](../../docs/ATIF-Experiment.md#automatic-derivation)
and [Stored form](../../docs/ATIF-Experiment.md#stored-form).

## Agent and framework evidence

Case-level `otel/spans.jsonl` contains Agent exports. Each line carries its own
resource, scope, trace identity and origin. Lines are derived from the byte-exact
exports archived under `otel/raw/`, and `archive` names the archived file. The
archive is unredacted, so the trajectory never points into it. `otel/status.json`
describes that collection window. Per-Input `framework.jsonl` contains adapter
callbacks. Historical rows without identifiable provenance have origin `unknown`.

An exact operation identifier can associate several independent evidence
references with one action. For OpenClaw, an accepted spawn, a child tool result,
and a completion notification have separate evidence requirements.
[Agent trace collection](../harness/otel/README.md)
