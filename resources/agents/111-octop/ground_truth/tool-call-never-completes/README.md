# Ground truth — Octop: tool calls never complete in a multi-call turn

Agent: `octop` (`resources/agents/111-octop`; upstream `TencentCloud/Octop` `dd9dce470844`,
release `v1.0.2` / PyPI `octop==1.0.2`), framework `acp`. The ACP server ships in
`octop-harness 1.0.4`.

## The defect

An ACP turn that issues more than one tool call does not report completion for all of them. The
client receives N `tool_call` notifications but fewer than N distinct `toolCallId`s reach a terminal
status, and one of the ids receives `completed` twice.

Cause, read from the pinned harness (`octop_harness/acp/server.py`, `_chunk_to_updates`):

```python
elif ctype == "tool_result":
    ...
    tool_id = next(iter(tool_id_buf.values()), uuid4().hex[:8])   # addressed by buffer position
    updates.append(update_tool_call(tool_id, status="completed", ...))
```

`tool_id_buf` is a per-turn dict keyed by `_idx_<index>`, so the terminal update is addressed by
position instead of by the call the result belongs to. With several calls in one turn the first
buffered entry absorbs every `completed` update and the remaining calls stay `in_progress` forever.

Client impact: a tool result cannot be attributed to the call that produced it, and completion cannot
be distinguished from an abandoned call. In ABB this surfaces as an evidence gap
(`acp_outcome_not_observed`) when the Judge checks whether the written files were produced by the
calls the Agent claims.

## Reproduction

Ten independent runs of the same frozen task shape (write two files, then run a command), each a new
ABB Suite and a new container. The task forces more than one tool call per turn, so the defect does
not depend on model sampling luck.

| run | suite case | tool calls | ids with terminal status | ids left in `in_progress` |
| --- | --- | --- | --- | --- |
| 1 | `167913a0b2bb` | 3 | 2 | 1 |
| 2 | `730295c106ff` | 4 | 3 | 1 |
| 3 | `f155a2e5dc7b` | 4 | 3 | 1 |
| 4 | `5836fa772765` | 3 | 2 | 1 |
| 5 | `22fe6b604c15` | 3 | 3 | 0 |
| 6 | `2693633448ca` | 3 | 2 | 1 |
| 7 | `ed905290ff48` | 3 | 2 | 1 |
| 8 | `3f5824435b84` | 4 | 2 | 2 |
| 9 | `c6ecec4350b4` | 3 | 2 | 1 |
| 10 | `61df623e19b5` | 5 | 3 | 2 |

**9 of 10 runs** leave at least one call without a terminal status (run 5 is the only clean one).
The packaged reference attempt is run 1 (`167913a0b2bb`, attempt `d53f0e15be4b`).

Scope note: the local SDK generates its own Case per run and does not accept a Case injected through
`sdk-options` (`case_collection` is a KUMA-SDK option; `case_artifact` is also ignored by the local
adapter), so the ten runs share a task shape rather than one artifact. `case.json` below is the
frozen Case of the packaged attempt. Re-running that exact Case, and adding single-call control
runs, needs the KUMA SDK path.

The unit under test is the merged one from `main` (`1061a09`). Its image build used a local PyPI
mirror because this machine cannot reach `pypi.org` at usable speed; that changes only where the
wheels came from, not what is installed.

## What the reference attempt shows

- `attempts/d53f0e15be4b/steps/0001/acp-events.jsonl`: three `tool_call` notifications with
  distinct ids, one id without any `completed`/`failed` update, one id with `completed` twice;
- the Agent's final answer is correct and both files exist, so this is not a task failure;
- the Judge records the missing completion as an evidence gap, not as an issue.

## Exclusions

- a single-call turn is unaffected (the only buffered id is the correct one);
- a wrong answer or a missing file is a different defect;
- a client that ignores ACP statuses and reads tool payloads from the transcript does not observe it.

## Files

| Path | Content |
| --- | --- |
| `gt.json` | machine-readable description and the selected reference attempt |
| `case.json`, `generation.json`, `publication.json` | frozen Case and its records |
| `attempts/d53f0e15be4b/` | native attempt tree (`run.json`, `steps/`, `judge/`, `evaluation/`, …) |
