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
[runtime]
secret_env_keys = ["SEARCH_API_KEY"]

[adapter]
type = "acp"
transport = "stdio"
command = ["mcode", "acp"]
cwd = "/workspace"
permission_policy = "allow_once"

[[adapter.mcp_servers]]
name = "search"
command = "/opt/agent/bin/search-mcp"
args = ["--stdio"]
env_keys = ["SEARCH_API_KEY"]
```

`command` is an argv array, not shell text. `cwd` must exist at execution time.
`input_key` optionally selects a text field from a structured input. Environment
forwarding includes runtime-declared keys, intercepted surrogate credentials,
process basics and CA/proxy settings; additional Agent settings use `env_keys`.
Credentials belong in the runtime's declared environment, never command arguments.

`[[adapter.mcp_servers]]` adds MCP servers to each new ACP session. The first
version supports stdio only. Each entry requires a unique `name` and an absolute
container `command`; `args` and `env_keys` default to empty arrays. `env_keys`
contains environment variable names, not values. Each name must also be declared
by the unit's runtime or adapter environment settings. ABB resolves the values
when starting the session and sends ACP v1's `env` array of `{name, value}`
objects. A declared but unset key fails before the ACP Agent starts. Secret values
are registered with redactors before the Agent starts. ABB redacts matching values
from observation artifacts and from the invocation output submitted to the
evaluation SDK. Values are never stored in `agent.toml`.

Do not set a `type` or `transport` field on an MCP entry: ACP v1 stdio server
objects have no discriminator. HTTP and SSE MCP servers are rejected explicitly;
HTTP needs capability negotiation, while SSE is deprecated. Entries without
`mcp_servers` continue to open sessions with an empty server list.

The adapter owns one event-loop thread for both sync and async calls. It starts the
Agent lazily, retains its session across inputs, rejects overlapping prompts and
permanently closes a failed session. A new attempt needs a new adapter. `close()`
and `aclose()` release the process group and loop; callers must close the adapter.

`end_turn` and `refusal` return output for the Judge to evaluate. Cancellation and
execution limits do not become successful results. A lost response is not evidence
that replay is safe. Protocol callbacks use the local `on_acp_event(name, data)`
observer seam; callback objects never cross the ACP wire.

Terminal references and the advertised `terminal_output` metadata extension are
resolved into tool evidence. See [ACP terminal evidence](../../observe/acp_evidence/README.md)
for the source Protocol, extension registry, limits and offline acceptance.
