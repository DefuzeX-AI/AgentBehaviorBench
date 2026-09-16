# Writing a BBA binding by hand

Read [the interface guide](assets/prompt.md), then choose a complete example:

1. [Direct graph export](assets/example-01-direct.md): a minimal forwarding factory.
2. [Async graph with input conversion](assets/example-02-async.md): Article Explainer.
3. [Full public task lifecycle](assets/example-03-native.md): TradingAgents.
4. [Application and resource lifecycle](assets/example-04-resources.md): Waku.

These are also the actual model instructions: `service.py` appends all four example
documents to `assets/prompt.md` for each requested binding. The package includes
these Markdown assets. Examples are snapshots, not imports of installed Agents.
Their source paths are reference labels, not evidence for an unrelated target.

## What we found in the current Agents

| Agent | Actual binding behavior | Lesson for a new integration |
| --- | --- | --- |
| Company Research | Constructs the native Graph, consumes its async run updates, extracts the editor report, forwards events and cleans job/client state. | Loading a graph alone may skip the application's required lifecycle. |
| ReAct | Compiles the upstream builder, adapts current message input, forwards config/context, verifies a final assistant response and returns answer plus messages. | Preserve callbacks and return the field selected by output_key. Its existing memory deployment is not a template for adding memory. |
| TradingAgents | Validates ticker/date, invokes public propagate, returns state and decision, owns private report/cache storage. | Call the public workflow rather than bypassing it with an internal graph. |
| GPT Researcher | Conducts research then writes a report; the current session binding also uses native report storage/chat APIs. | One research method may not produce the final report. Do not copy the session/memory design into this initial generator. |
| Waku | Initializes settings, storage and connection, invokes native respond, returns LoopResult and closes owned resources. | Cleanup, writable storage and observation limitations must be explicit. |
| Article Explainer | Converts current text to a user message, awaits the native compiled swarm and returns the complete state. | A small boundary wrapper is sufficient only when the native graph already owns the full workflow. |
| Data Enrichment | Its exported graph needs no input/output conversion. | New integrations use a forwarding factory returning that graph; no wrapper class is needed. |

Existing bindings are under `resources/agents/<unit>/bindings/`. They include
Agent-specific deployment decisions, and are not universal supported defaults.

## Manual authoring steps

1. Read the upstream entrypoint and the CLI/application that calls it. Write down
   the real input, final output and public execution sequence. Identify imports,
   dependencies and any external services from source rather than guessing.
2. Check the saved manifest. `bridge.py:create_graph` means the OUTER file
   `bindings/bridge.py` exports `create_graph`. The source graph config and graph ID
   still have to exist even when a binding overrides the loaded entrypoint.
3. Copy the appropriate pattern, replace only names/APIs verified in your source,
   and write the complete factory, invocation and owned-resource cleanup methods.
   Keep the original source unchanged. Do not copy another Agent's model, tools,
   memory configuration or network policy merely to make it run.
4. Make the input transformation explicit. Preserve RunnableConfig and supported
   context. Match output_key, propagate native failures, and describe unsupported
   inputs rather than silently dropping fields.
5. Ensure Docker installs the upstream package/dependencies and copies bindings
   into the unit's bindings directory. Provide declared environment/service
   configuration through the normal runtime, not hardcoded credentials.
6. Check syntax and export names, then use the existing certification flow for
   construction/loading checks. A real invocation is still needed to verify input,
   final output, callbacks, external services and cleanup. Syntax validation and
   an example template cannot establish that the complete Agent works.

An async smoke call uses `await adapter.ainvoke(value, run_config=...)` and finally
`await adapter.aclose()`; a synchronous caller uses `adapter.invoke(...)` and
finally `adapter.close()`. The adapter is
`agentbench.adapter.langgraph.adapter.LangGraphAdapter.from_agent_dir(unit_path)`.
Run such calls in the configured Agent environment; they execute the real Agent
and may consume provider credits. Never treat a mocked test as live certification.
