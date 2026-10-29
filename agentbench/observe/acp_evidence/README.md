# ACP terminal evidence

The observer resolves ACP terminal content by protocol type and terminal ID, not
by Agent identity. The reference format follows the [ACP terminal contract](https://agentclientprotocol.com/protocol/v1/terminals). `TerminalEvidenceSource.snapshot()` supplies observed JSON
fields. `ToolEvidence` assembles them into the existing tool-result semantic
attribute; generic OTel and evaluation SDK code do not interpret ACP terminals.

`TerminalSnapshots` retains client callback snapshots, including the final
release snapshot after the live terminal has been deleted. At the prompt or
failure boundary the ACP adapter also snapshots still-active terminals without
rerunning commands or waiting for them to exit. Client terminal output combines
stdout and stderr, as the existing ACP terminal implementation does.

`TerminalEvidenceExtension` adds typed extension codecs. Register a codec in
`TERMINAL_EXTENSIONS`; its capability advertisement, update parser and snapshot
lookup stay together. The included `terminal_output` codec recognizes only
`_meta.terminal_info`, `terminal_output`, and `terminal_exit`, with explicit
`terminal_id` values. It appends output chunks in order. Other metadata is opaque.

Results distinguish `client_observed` from `agent_reported` evidence. Agent data
cannot overwrite a client snapshot with the same ID; additional sources are kept
separately. Existing raw output and non-terminal content remain in the result.
An empty observed output is different from `output_status: not_observed`.
Missing exit status remains `exit_status: not_observed`, never inferred from a
tool's completed/failed status.

Each source retains at most 256 terminal IDs per invocation/tool and 64 KiB of
UTF-8 output per terminal, keeping the tail at character boundaries. Projection
truncation sets `truncated` and `evidence_truncated`; client truncation is retained.
Credential redaction precedes truncation and ordinary trace redaction also applies.
Full protocol events remain in local artifacts. Terminal events do not become
empty root span events, which would consume the SDK's bounded event budget.

Terminal-backed tool spans stay open until the prompt/failure boundary so that
output received after the reported final status (including release) is retained.
At that boundary the observed final status and any partial evidence are emitted;
unobserved terminal fields are explicit. Tools without a reported final outcome
continue to use the existing `acp_outcome_not_observed` control marker. Deferred
span closure records the end of observation, not a claimed native process duration.

Regression coverage lives in `tests/test_issue277.py`. For offline Linux Docker
acceptance with the pinned ACP/KUMA dependencies installed, run
`python -m tests.sdk_fixtures.acp_terminal_acceptance <output-directory>` with
networking disabled. It runs a real ACP stdio peer and command, and retains Case,
Agent output, SDK evidence and a custom Judge report that checks both terminal
paths plus a real stdio MCP tool call. No production model or Backend is called.
