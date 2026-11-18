# DotCraft current-head run — 2026-11-05

Branch head `1d4bfa2da` merges main `55a093f94`. Its diff from main is limited to
`resources/agents/141-dotcraft/`, its registry entry and `tests/test_issue492.py`;
no ABB production source is changed. The unit moved from slot 127 (now used
by main) to 141.

## Checks

- `tests/test_issue492.py`, manifest generation/credential, ACP config and
  registry-step tests: **49 passed**.

## Real CLI Case on unchanged ABB

`agentbench evaluate dotcraft --sdk local --cases 1 --max-steps 2 --timeout 1200
--case-retries 0` with a temporary enabled registry, model
`doubao-seed-2-1-lite-260915` (shared OpenAI-compatible selection), local Judge.

- Suite `suite_880dd1b5cac246ebbb8f6b6353fc6a82`, attempt
  `e1a998091ed5478c89f87c6deedc6a89`. Generated Case: create `palindrome.py`
  and a `unittest` file, then run the tests.
- Execution `succeeded`, host Trace validation `succeeded`, cleanup `succeeded`.
  8 model requests to the selected endpoint. ACP reported 5 tool calls
  (CodeMode, WriteFile ×2, Exec, CodeMode), none incomplete. The native answer
  reports both files, four test cases and exit status 0.
- **Quality gate failed.** The local Judge returned `pass` (medium) with two
  evidence gaps: WriteFile/Exec spans have no arguments, file contents,
  stdout or exit code. ABB refuses a pass that carries evidence gaps
  (`ValueError: Judge cannot pass with evidence gaps`).

## Cause

DotCraft 0.9.4's native ACP bridge emits `tool_call` with `content: null` and
`tool_call_update` with `content: []` for these tools. The bridge
(`src/DotCraft.App/Acp/AcpBridgeHandler.cs`) only fills content when the app
server item carries arguments/results, which it did not here. ABB's ACP
coverage is `tool_calls=acp`, `file_changes=not_observed`, so the Judge has no
independent tool evidence.

A local trial with the documented native setting `Tools.CodeMode.Mode = "Off"`
(direct tool calls) produced the same empty ACP content and the same Judge
outcome (Suite `suite_112b920de3bd411796e7610b72ebc6a1`). That setting was not
kept; the unit still runs DotCraft's default `Only` mode.

Earlier preparation failures on this head were host-side: a macOS temporary
directory symlink rejected by ABB's path check (fixed by running with a
non-symlinked `TMPDIR`) and Docker build `apt` fetch errors through the local
network proxy. Neither involved the Agent.

## Status

Not accepted. The integration runs end to end on unchanged ABB, but the
native ACP stream does not carry the tool evidence the Judge needs. Options
are an upstream DotCraft change that fills ACP tool content, or a maintainer
decision on how ACP Agents with empty tool payloads are judged. The registry
entry stays `enabled = false`, `status = "adapting"`.
