# ACP adapter

The adapter implements ABB's existing invocation contract using the official
`agent-client-protocol==0.12.1` Python SDK. Install the `acp` project extra for host
protocol tests. The SDK must also be installed in an ACP Agent image's worker
interpreter; copying ABB source into an image does not install dependencies.

Current implementation: stdio handshake, optional explicit authentication,
Case-owned sessions, text inputs, streamed text output, permission decisions,
error/stop handling, workspace file callbacks, bounded terminal output and
process-group cleanup. Tool notifications project live OTel spans and retain raw
ACP evidence; missing fields stay missing. This is not itself a certified Agent
unit. The generic worker build overlay installs the adapter requirements file.

```toml
[adapter]
type = "acp"
transport = "stdio"
command = ["mcode", "acp"]
cwd = "/workspace"
permission_policy = "allow_once"
```

`command` is an argv array, not shell text. `cwd` must exist at execution time.
`input_key` optionally selects a text field from a structured input. Environment
forwarding includes runtime-declared keys, intercepted surrogate credentials,
process basics and CA/proxy settings; additional Agent settings use `env_keys`.
Credentials belong in the runtime's declared environment, never command arguments.

The adapter owns one event-loop thread for both sync and async calls. It starts the
Agent lazily, retains its session across inputs, rejects overlapping prompts and
permanently closes a failed session. A new attempt needs a new adapter. `close()`
and `aclose()` release the process group and loop; callers must close the adapter.

`end_turn` and `refusal` return output for the Judge to evaluate. Cancellation and
execution limits do not become successful results. A lost response is not evidence
that replay is safe. Protocol callbacks use the local `on_acp_event(name, data)`
observer seam; callback objects never cross the ACP wire.

An optional `evidence_reader = "bootstrap/native_evidence.py:read_calls"` reads
documented native evidence after a prompt returns. The default signature is
`read_calls(session_id)`. A reader may explicitly declare
`read_calls(session_id, *, prompt_response)` to receive a detached JSON-compatible
copy of that **same** native ACP response, including `_meta`. This allows a
reader to select a committed native checkpoint without timing heuristics. The
adapter does not interpret vendor metadata or change prompts/model traffic.
Return bounded `native_model_call` records with native session/call/response IDs;
missing evidence must not be invented. Reader exceptions emit a failed
`native_evidence_status` without replacing the Agent's answer. Legacy readers
are still called with only `session_id`.
