# LangGraph adapter

This adapter follows LangGraph's official application contract:

- `langgraph.json` owns graph discovery through `graphs.<graph_id>`.
- An entrypoint uses `file.py:attribute` and may expose a compiled graph,
  Functional API entrypoint, Pregel object, or zero-argument graph factory.
- AgentBehaviorBench (ABB) checks behavior through `invoke()` instead of depending on a
  concrete LangGraph implementation class.

The ABB-specific `agent.toml` selects the graph and maps benchmark values:

```toml
[adapter]
type = "langgraph"
mode = "in_process"
config = "langgraph.json"
graph_id = "agent"
input_key = "prompt"
output_key = "response"
```

Execution flow:

```text
registry -> <unit>/agent.toml -> <unit>/agent/langgraph.json
         -> <unit>/agent/file.py:graph -> graph.invoke() / graph.ainvoke()
```

`LangGraphInvocation` preserves both the extracted benchmark output and the raw
graph state. The SDK-facing harness can submit `output` while retaining
`raw_output` as evidence.

`agent_root` is the outer ABB unit; `source_root` is its `agent/` checkout.
Both `adapter.config` and graph entrypoints are relative to `source_root`.
The loader supports packages at the source root or inside its `src/` directory.

This adapter runs in-process, where package names and dependencies can collide.
For `runtime.type = "docker"`, RuntimeFactory instead selects the container
adapter and executes `launch.argv`; it does not import the upstream graph on
the host. See [Agent unit layout](../../../docs/Agents/Layout.md).

Official references:

- https://docs.langchain.com/oss/python/langgraph/application-structure
- https://docs.langchain.com/oss/python/langgraph/use-functional-api
- https://github.com/langchain-ai/langgraph/blob/main/libs/cli/langgraph_cli/schemas.py
