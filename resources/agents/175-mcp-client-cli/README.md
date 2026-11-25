# MCP Client CLI in ABB

This integration follows the native CLI's LangGraph construction using the
upstream `AgentState`, `load_tools`, model factory, prompt, `SqliteStore`,
`AsyncSqliteSaver` and `ConversationManager`. It forwards RunnableConfig and
returns the complete final graph state. Native errors propagate to ABB.

## Windows, macOS and Linux

Use Docker with Linux containers, activate the ABB environment, and run from
the ABB repository root:

```sh
python -m agentbench evaluate mcp-client-cli --sdk native --case-file resources/agents/175-mcp-client-cli/smoke-case.json --cases 1 --max-steps 1 --no-view -y --results-dir cache/mcp-client-cli-smoke
```

Docker Desktop provides Linux containers on Windows/macOS; Docker Engine or
Desktop works on Linux. The Dockerfile contains no fixed CPU architecture or
host drive paths. It installs the pinned UV lock and native package, plus ABB
worker dependencies. The container user owns its home, memory DB and cache.
ABB supplies `.abb-runtime` during its managed build.

## Configuration and tools

At image build time, `bootstrap/configure.py` creates the native
`/opt/agent/mcp-server-config.json`, which was missing from the original unit.
Its system prompt is copied byte-for-byte as a string from the upstream example.
The example model/provider/temperature are retained; the example's literal API
key placeholder is omitted so the native loader reads the interceptor-injected
`OPENAI_API_KEY` environment variable.

This initial configuration has no external MCP servers. The upstream example
lists fetch, Brave Search, YouTube and command-execution services; these require
separate installation/configuration and sometimes credentials. They are not
preinstalled native tools. Native `load_tools(no_tools=False)` still adds the
built-in `save_memory` tool. The binding does not use the old generated `tools=[]`
shortcut, erase loaded memories, or disable checkpointing.

Add external servers in the deployment's native configuration, provision their
executables and credentials, and declare scoped tool-egress routes when needed.
The native confirmation check remains active. This greeting test does not
validate external MCP integrations or interactive approvals.

## Model interception

The existing native OpenAI Chat Completions route and interceptor-managed
credential remain in `agent.toml`. In `replace` mode ABB owns the real provider
credentials and actual target model. The source-side `gpt-4o-mini` label identifies
the native request; it does not pin the replacement model. No mode is hardcoded
in the binding. Inspect the actual input reply, trajectory and network evidence
together before claiming that execution succeeded.
