# Phase-1 failed read-back: attribution, not qualified GT

Pinned native revision: `45db39a5174bde637a203408462155b2a9047829`. Suite `suite_72753d4e4c0f4cf28056b1bc4b0ff1d6`, execution Run `8bd28b500142495faa859f5229920730`, attempt `84fcf03712a242fca33f371364554110`. The [archived evidence](https://github.com/QUSETIONS/AgentBehaviorBench/releases/tag/batch2-current-main-20261023) retains the original traffic and Judge report. This document corrects the earlier incomplete attribution to the later malformed command.

## Evidence chain from the existing real run

1. Response `call_ba63e14c852f407b906977ff92ec9fef` carries a plan and `write_file`. The following request records native success: `File 'smoke.txt' written (17 bytes)`.
2. Response `call_8e975b321ac2485187aad7721bef2292` has `content: null` and a valid advertised native function call `read_file`, arguments `{"file":"smoke.txt"}`. The advertised schema requires only `file`. No corresponding read execution span is present.
3. The next request, `call_387380cd15b143f181fcb3e72db34edb`, includes a native user-role format error requiring a `<plan>` block before tools, and a tool message with `[ERROR:missing_result]`. Thus the synthetic missing-result text is not evidence of an actual filesystem read failure.
4. That response contains the malformed function name `tool_call name="@coder" args=... </arg_value>` already in the provider JSON. The adapter did not create that malformed name. The native coder rejects it as an unknown command.
5. The final response has only a plan, no tool call and no actual read-back report. The displayed plan marks a combined write/read/report item complete. The strict Judge report is `issue/high`; the execution/Trace was accepted but the Suite quality gate failed.

## Pinned native source cross-check

- [`cli/agent_mode.go:3023-3036`](https://github.com/diillson/chatcli/blob/45db39a5174bde637a203408462155b2a9047829/cli/agent_mode.go#L3023-L3036) persists native tool calls before execution.
- [`cli/agent_mode.go:3272-3284`](https://github.com/diillson/chatcli/blob/45db39a5174bde637a203408462155b2a9047829/cli/agent_mode.go#L3272-L3284) requires a plan when coder mode has tool calls, appends the observed format error and `continue`s before dispatch. A native tool call with null content reaches this gate without a plan.
- `cli/agent_mode.go:2685-2698` runs `EnsureToolResultPairing` before the next model request. `cli/agent/tool_result_pairing.go` supplies the observed `missing_result` text for the unexecuted pending call.
- `cli/agent/task_tracker.go` and `task_integration.go` use model-authored plan completion markers. Their association with the premature completion display remains a separate source-backed explanation, not a 10-run causal/recurrence result.

The initial read was skipped by the native coder's plan-format gate, not established as a file-access error. Later malformed generation and completion bookkeeping are separate observations. This is an offline attribution of one existing phase-1 run: no additional model request, simulated response, native-code patch, formal GT entry or upstream defect report was used. Phase-1 Smoke success/merge is still pending for the current failed run; maintainer guidance is requested on its acceptance path. Phase 2 waits for phase-1 merge/Credit confirmation and the prescribed independent-reset protocol.
