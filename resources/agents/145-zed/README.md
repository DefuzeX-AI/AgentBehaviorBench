# Zed native agent

This unit runs the official `eval-cli` from the pinned Zed source with the
single settings serialization correction described below. The outer
ACP bridge transports one text prompt to its stdin and replays actual native
messages and tool results from `thread.json`. It does not implement an agent
loop. A second prompt in the same session is rejected:
the upstream CLI does not expose a session resume API.

`Dockerfile.builder` follows the upstream static Linux build. Build it once from
this unit directory before running ABB:

```sh
docker build --platform linux/amd64 --target builder -f Dockerfile.builder -t abb-zed-builder:2f808b3-settings-fix .
```

The runtime `Dockerfile` copies that builder's `/eval-cli` and adds the ABB worker.
Compilation requires substantial disk space and time. Source is restored from
the full Git commit in `agent.toml`; a fresh machine must build the native image
with the command above before ABB execution.

The pinned upstream `crates/eval_cli/src/main.rs` appends an extra quote to the
settings JSON in `run_agent`, causing startup to fail with `trailing characters`.
`bootstrap/fix-settings-json.pl` removes exactly that quote in the disposable
build copy and fails on unexpected source changes. The downloaded `agent/`
checkout remains unchanged. This correction does not change prompts, tools,
model selection, or the native agent loop.

Model configuration uses runtime-owned `ABB_AGENT_MODEL_*` values mapped to
Zed's official `ZED_OPENAI_COMPATIBLE_PROVIDERS` setting. ABB model interception
follows the host's `ACP_MODEL_MODE` switch (replace by default). No provider is pinned. The bridge leaves
the native tool set enabled. Native `result.json`, `thread.json`, `thread.md`
and process logs are retained under `.zed-evidence/` in the workspace.

Run a fixed single-prompt case with ABB's native SDK and inspect both execution
status and `trajectory.json`. The CLI can close a response stream after receiving
the final answer and cancel its background conversation-title request at process
exit. ABB preserves those transport errors, so a successful native reply may
coexist with a `partial` trajectory. Do not describe that as complete wire evidence.
