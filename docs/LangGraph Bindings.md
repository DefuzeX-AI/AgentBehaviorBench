# Writing LangGraph bindings

English | [中文](otherLanguages/LangGraph%20Bindings.zh-CN.md)

[Add an Agent](How%20To%20Add%20Agent.md) · [Agent units](Agents.md)

This handbook explains how to write the Python files in an ABB LangGraph Agent unit's `bindings/` directory. A binding loads the real Agent, translates the current input into its native interface, preserves execution configuration, returns its actual result and releases owned resources. Its implementation must follow the source application, including setup performed by its public caller.

The interface descriptions below reflect ABB's current loader and adapter. The writing rules explain how to preserve the native application; static acceptance alone does not demonstrate correct execution or complete observation. Native ACP integrations use their protocol configuration instead of this Python binding contract.

## File layout and manifest selection

```text
resources/agents/NN-name/
  agent.toml
  agent/                       # Imported source and its existing resources
  bindings/
    bridge.py                  # Factory selected by agent.toml
  Dockerfile
  .dockerignore
  requirement.md
```

Use a descriptive filename such as `bridge.py` or `research_bridge.py`. This adapter-only TOML example selects `bindings/bridge.py:create_graph`:

```toml
[adapter]
type = "langgraph"
mode = "in_process"
binding = "bridge.py:create_graph"
input_key = "message"
```

This is part of a manifest, not a complete Docker deployment. `binding` is relative to the outer `bindings/`; do not write `bindings/bridge.py:create_graph` in that field. The current configuration reader supports omitting both `config` and `graph_id` when the binding is the entrypoint. TOML has no null value: omit the fields rather than writing `config = null`.

If the source already has a suitable descriptor, retain its exact path and graph name:

```toml
config = "langgraph.json"
graph_id = "agent"
```

These two lines belong in `[adapter]`. `config` is relative to `agent/`, and its `graphs` object must contain the selected name. When `binding` is present, ABB loads the outer binding; the JSON descriptor does not automatically perform the native application's setup. Keep integration files outside the imported source.

## What ABB calls

```text
Current Case input
  -> adapter input mapping
  -> binding.invoke(value, config=...) or await binding.ainvoke(...)
  -> native application
  -> binding result
  -> adapter output mapping and retained raw_output
```

### How Case inputs reach the binding

**ABB does not pass the whole Case to `create_graph()`. It creates an Agent instance, then passes each current Case input to `invoke()` or `ainvoke()`.** After the binding returns, ABB submits the result to the SDK. The binding itself does not call the SDK submission interface.

Suppose a conversational Case contains two steps:

```text
Step 1: Research OpenAI
Step 2: Focus on its product information
```

This simplified example assumes the binding provides `ainvoke` and `aclose`. Adapter mapping, observation configuration and the implementation of SDK submission are temporarily omitted:

```python
# Create one Agent instance for this Case
agent = create_graph()
config = {
    "configurable": {"thread_id": "case-session-001"}
}

try:
    # Step 1: deliver the current input
    result1 = await agent.ainvoke(
        "Research OpenAI",
        config=config,
    )
    # ABB submits result1 to the SDK

    # Step 2: reuse the same instance and session ID
    result2 = await agent.ainvoke(
        "Focus on its product information",
        config=config,
    )
    # ABB submits result2 to the SDK
finally:
    # Release resources after completion or failure
    await agent.aclose()
```

For a native object with only synchronous `invoke`, ABB calls it in a worker thread. If cleanup has only synchronous `close`, ABB calls `close`. The example explains the order; it does not ask the binding to implement a Case scheduler.

### How the adapter wraps the current input

The actual adapter sits between SDK input and the binding. Suppose `agent.toml` includes:

```toml
[adapter]
input_key = "message"
```

This fragment explains mapping only; retain the other adapter fields from the complete table above. When the SDK supplies the text `"Research OpenAI"`, ABB passes this value to the binding:

```python
await agent.ainvoke(
    {"message": "Research OpenAI"},
    config=config,
)
```

Inside the binding, processing can therefore be understood as:

```python
async def ainvoke(self, value, config=None):
    # value is the current input; assume fields have already been validated here
    text = value["message"]

    # Translate to the real LangGraph's input state
    state = {
        "messages": [{"role": "user", "content": text}]
    }

    # Execute the real Agent and return its result to ABB
    return await self._graph.ainvoke(state, config=config)
```

This fragment assumes the native graph accepts `messages`; the later template shows complete input validation. ABB applies the adapter's `output_key`, submits the resulting output to the SDK and retains `raw_output`. An input that is already a mapping is not wrapped again.

- The current Case input enters `value`.
- Session, observation and other execution configuration enters `config`.
- `create_graph()` creates the instance; it does not receive the Case.
- ABB delivers only the current input, without an automatically assembled history. History belongs to the native Agent's existing session or checkpoint. Reusing an instance does not automatically give a stateless Agent conversational memory.

### Function interface reference

| Export or method | Required behavior |
| --- | --- |
| `def create_graph()` | An undecorated synchronous factory callable without arguments. Return an object with callable `invoke`; never a coroutine or generator. |
| `def invoke(self, value, config=None)` | Execute one input and return the documented final result. Required even when the native application is asynchronous. |
| `async def ainvoke(self, value, config=None)` | Optional for synchronous applications; implement for asynchronous execution. Return the final result rather than yielding events. |
| Keyword-only `context=None` | Accept when `[adapter.context]` is configured, and convert it to the supported native context type. |
| `close()` or `aclose()` | Release resources this instance owns. Make cleanup safe to repeat and after partial initialization. |

At the adapter layer the argument is named `run_config`; at the binding layer it is passed as `config`. Accepting the keyword is necessary, but preserving it inside the native call is a separate responsibility. ABB's async adapter uses `ainvoke` when available; otherwise it runs `invoke` in a worker thread. A synchronous-only native API that requires the main thread needs an explicit compatible execution approach, rather than automatic thread offloading.

In a Docker worker, observation callbacks are created inside the process. Host callback objects cannot cross the JSON request boundary. The binding receives the worker's live configuration and must not serialize it.

## Establish the native contract before writing

Read the public CLI, application or example that actually runs the selected Agent. Record these facts in the module docstring and use them to implement the binding:

| Question | Evidence to find |
| --- | --- |
| What is the public entrypoint? | Exact source module, factory/class, constructor arguments and execution method. |
| What does one input contain? | Required business fields, accepted types and the caller's initial state. |
| What setup happens before execution? | Model clients, hardware configuration, datasets, directories, databases or sessions. |
| What marks completion? | Final report/message/state and the public caller's failure condition. |
| Where does execution configuration go? | Native `config` parameter or a verified framework context mechanism. |
| What persists within a Case? | Native checkpoint, session, workspace and resource ownership. |

ABB invokes the binding directly. It does not automatically run an upstream CLI that parses JSON, creates state, starts services or prepares writable paths. Reproduce the necessary public lifecycle without replacing the Agent's reasoning or tools. If required business inputs or deployment choices are unknown, report the missing information during onboarding; do not invent values to make the binding load.

## Choose the smallest compatible implementation

### Return the native Agent directly

Use this when the returned native object already accepts the adapter's input, supports `config`, returns the intended output and owns its resource cleanup. For example, the Folder Mover's current native object accepts text or exactly `{"message": text}` and exposes its own invocation and cleanup methods:

```python
"""Expose folder_mover's public Agent without changing its input or lifecycle."""


def create_graph():
    """Return a fresh native Agent; input example: {'message': 'Explain your tool'}."""
    from folder_mover import create_graph as native_create_graph
    return native_create_graph()
```

This example requires the Folder Mover source and dependencies in the worker's import path. A compiled graph expecting `{"messages": [...]}` cannot be returned unchanged when the SDK sends text or `{"message": text}`. `input_key = "message"` does not convert that field into `messages`.

### Translate text into native graph state

The following template assumes the verified native factory returns a synchronous invokable graph whose input is `messages`, whose result should remain unchanged, and whose owned cleanup method is `close`. Replace `upstream_agent.graph` and the factory name with the confirmed source API before using it. If those assumptions differ, implement the native lifecycle instead of copying this template.

```python
"""Translate one current message to native messages state.

Input: text or exactly {'message': nonempty_text}.
Config: forwarded unchanged to the native graph.
Output: the complete native result, without an output_key extraction here.
Errors: invalid input and native failures propagate.
Ownership: this instance owns the graph returned by the native factory.
"""
from collections.abc import Mapping


def state_from_input(value):
    if isinstance(value, Mapping):
        if set(value) != {"message"}:
            raise ValueError("Supply exactly one message field")
        value = value["message"]
    if not isinstance(value, str) or not value.strip():
        raise ValueError("message must be a non-empty string")
    return {"messages": [{"role": "user", "content": value}]}


class AgentGraph:
    def __init__(self):
        from upstream_agent.graph import create_graph as create_native_graph
        self._native = create_native_graph()

    def invoke(self, value, config=None):
        if self._native is None:
            raise RuntimeError("Binding is closed")
        return self._native.invoke(state_from_input(value), config=config)

    def close(self):
        native, self._native = self._native, None
        close = getattr(native, "close", None)
        if callable(close):
            close()


def create_graph():
    """Return a fresh binding; example input: {'message': 'Explain this text'}."""
    return AgentGraph()
```

This synchronous template can be driven by ABB's async adapter when native execution and resources are safe in a worker thread. For a native graph supporting both sync and async execution, replace the invocation/cleanup methods inside `AgentGraph` with the following methods; keep its constructor, input helper and factory:

```python
def invoke(self, value, config=None):
    if self._native is None:
        raise RuntimeError("Binding is closed")
    return self._native.invoke(state_from_input(value), config=config)


async def ainvoke(self, value, config=None):
    if self._native is None:
        raise RuntimeError("Binding is closed")
    return await self._native.ainvoke(state_from_input(value), config=config)


def close(self):
    native, self._native = self._native, None
    close_native = getattr(native, "close", None)
    if callable(close_native):
        close_native()


async def aclose(self):
    native, self._native = self._native, None
    close_native = getattr(native, "aclose", None)
    if callable(close_native):
        await close_native()
    else:
        close_native = getattr(native, "close", None)
        if callable(close_native):
            close_native()
```

Indent these methods into the class. ABB's async cleanup prefers `aclose`; clients with async resources require the async path to release them. Do not use the sync `close` path to discard resources that need awaited cleanup.

When a graph contains async-only nodes, provide `ainvoke` and have a sync bridge call `asyncio.run(self.ainvoke(value, config))` only for callers without an active event loop. Never call `asyncio.run` inside `ainvoke`. Repeated new loops are unsafe for clients tied to an earlier loop; design initialization and cleanup for the native library's loop requirements.

## Preserve config and distinguish context

Pass `config=config` directly when the native API supports it. Configuration may contain callbacks, tags, metadata, `configurable.thread_id` and execution limits. It is not the business input, and `configurable` is not interchangeable with the native runtime context.

When an explicit deployment setting adds a default execution limit, merge without mutating the incoming object:

```python
run_config = dict(config or {})
run_config.setdefault("recursion_limit", 50)
result = await self._native.ainvoke(state, config=run_config)
```

The limit above is illustrative, not a universal recommendation. Copy a nested dictionary before changing it, preserve unrelated keys and never overwrite the supplied Case thread identity with a random ID on every call. Keep live callback objects intact; do not deepcopy or JSON-encode the configuration.

For a native context schema, implement the separate keyword and construct the native type only when that API supports it. The ReAct binding, for example, accepts `context=None` and calls its graph with `context=Context(**dict(context or {}))` alongside `config=config`. Keep secrets in the declared credential environment rather than the context table.

If the public execution method has no config parameter, do not pass an unsupported keyword or bypass necessary setup by calling a lower-level graph. The current TradingAgents integration uses this verified LangChain mechanism around `propagate`:

```python
from langchain_core.runnables.config import set_config_context

with set_config_context(dict(config or {})) as invocation_context:
    final_state, decision = invocation_context.run(
        native.propagate, ticker, trade_date
    )
```

Here `native`, `ticker` and `trade_date` are already constructed and validated. This fragment depends on the target's installed LangChain version and does not apply to every library. If there is no compatible mechanism, state the observation limitation explicitly. Forwarding configuration alone does not prove that all native tools and calls emit evidence.

## Implement business inputs and streamed workflows

`input_key` wraps non-mapping inputs only; mappings pass through unchanged. Validate the accepted keys and types in the binding. Do not silently discard unsupported fields, reuse a previous ticker/date to fill a new request, or mistake a string containing JSON for an already parsed mapping.

The current KUMA onboarding flow uses text Case inputs, including ordinary natural-language requests. A Profile asking for JSON does not enforce JSON serialization. Preserve the complete request in a source-confirmed native problem/message field or questions list, with optional fields retaining their native defaults. A documented JSON problem format may be supported as an additional validated input format; do not require every text Case to pass `json.loads`. Reproduce the public caller's state construction. If no faithful mapping exists because required business data is missing, report the incompatibility rather than guessing values. A locally accepted structured profile does not establish remote Case support.

| Native workflow | What belongs in the binding |
| --- | --- |
| Company research | Validate company and optional metadata, construct `Graph` with those inputs, then consume `run(config)`. |
| CAD generation | Obtain `get_default_initial_state()` and set the current `user_request`. |
| Laboratory protocol generation | Load the declared hardware profile and knowledge, initialize attempt state, then use native async execution. |
| Data analysis | Supply a real configured DataFrame as well as user instructions; describe whether data is fixed or caller-supplied. |
| Trading analysis | Validate the explicitly supplied ticker and date before `propagate`. |
| GPT Researcher | Build the complete documented task, including `publish_formats`, then execute the native research team. |

Public async generators require consumption inside `ainvoke`. For the current Company Research interface, the important call shape is:

```python
# NativeGraph is the verified upstream class, not a replacement implementation.
native = NativeGraph(company=company, job_id=job_id)
report = None
async for update in native.run(config):
    editor = update.get("editor") if isinstance(update, dict) else None
    if isinstance(editor, dict) and "report" in editor:
        report = editor["report"]
if not isinstance(report, str) or not report.strip():
    raise RuntimeError("Native workflow completed without its final report")
return {"report": report}
```

This is a fragment inside an async method: input validation, optional metadata, resource cleanup and progress observation must follow the actual native application. Returning `native.run(config)` would return an iterator rather than execute the workflow to its final result.

## Return results and preserve failures

Without `output_key`, ABB submits the entire binding return value and retains it as `raw_output`. With `output_key = "report"`, return a mapping containing `report`; ABB extracts that field as `output` while retaining the complete mapping. Returning a string or only `messages` is incompatible with that setting.

Prefer the native final result. If a deployment intentionally projects a text answer, identify the native field used and retain necessary state or report evidence. Match the public application's completion condition: some return a full state, others require a final report or assistant response. Do not invent quality checks or treat intermediate tool output as the final deliverable.

Let native execution exceptions propagate. Do not turn them into a success-looking `{"answer": "An error occurred"}`. Keep error messages free of credentials. A native tool error that the Agent handles and explains is different from a binding or runtime failure; preserve the native handling.

## Own resources and preserve native sessions

The worker reuses one Agent instance across Inputs in a Case and provides a stable thread ID. It delivers only the current input; it does not assemble conversation history. Preserve the native application's intended session behavior. Do not add a transcript, checkpoint or memory mechanism merely to make a stateless workflow remember earlier Inputs. Do not share mutable state across independent Cases.

Initialize reusable resources once or lazily on first invocation as required by the native API. For async bootstrap, keep the factory synchronous and perform awaited setup in `ainvoke`. Track what the instance owns: clients, database processes, connections and private temporary directories. Release those resources on shutdown and partial initialization failure. If ownership begins before the factory returns, the constructor or factory must clean up its own failed setup because ABB has no completed instance to close.

Resolve packaged assets relative to `__file__`, for example `Path(__file__).resolve().parents[1] / "agent" / "data" / "dataset.csv"`. Use explicitly configured writable locations for generated files. Changing the process working directory affects the whole process and should be limited to an isolated worker with restoration where appropriate. Private temporary files are not automatically persistent benchmark artifacts.

Docker must install the actual dependencies and copy the binding beside the selected Agent root. The worker defaults to `--agent-root /opt/agent`; `launch.workdir` is the process working directory and may differ from that root. The current static layout checker uses `launch.workdir` when locating bindings, so layouts using `/tmp` for execution and `/opt/agent` for source can be rejected. Resolve that mismatch against the checker and worker behavior; this handbook does not change the checker or establish runtime success.

Declare model routes and tool routes in `agent.toml`, and non-HTTP service routing where needed. Starting a required local service remains the native lifecycle or binding's responsibility; declaring its route does not start it. Do not install dependencies, alter network interception or embed credentials in the binding.

## Repository examples

These links identify useful implementation patterns. Review the source and manifest together; existing bindings can have limitations and are not universal templates. The list records the current implementation, not certification status.

| Unit | Useful pattern or review point |
| --- | --- |
| [01 Folder Mover](../resources/agents/01-folder-mover-agent/bindings/bridge.py) | Direct native factory; actual input validation is in `agent/folder_mover.py`. |
| [02 Company Research](../resources/agents/02-company-research-agent/bindings/company_research_agent.py) | Constructor business inputs, async stream consumption and final report. |
| [03 ReAct](../resources/agents/03-react-agent/bindings/bridge.py) | Text/messages conversion, native context and config forwarding. |
| [04 Crypto Hedge Fund](../resources/agents/04-ai-hedge-fund-crypto/bindings/bridge.py) | Configured portfolio and market state; review missing config forwarding. |
| [05 LabScript](../resources/agents/05-labscript-ai/bindings/bridge.py) | Hardware state and async-only graph; review config replacement. |
| [06 Multi Agent CAD](../resources/agents/06-multi-agent-cad/bindings/bridge.py) | Native default state and merged recursion configuration. |
| [07 Autoresearch](../resources/agents/07-autoresearch-agents/bindings/bridge.py) | Calculator/converter Agent; currently discards incoming config. |
| [08 Streamlit Template](../resources/agents/08-langchain-streamlit-template/bindings/bridge.py) | Extract the native factory without starting UI; review private thread config. |
| [09 Curiosity](../resources/agents/09-curiosity/bindings/bridge.py) | SQLite path and native thread; review private thread config. |
| [10 Readwren](../resources/agents/10-readwren/bindings/bridge.py) | Start interview before sending input; public method has no config parameter. |
| [11 TableGPT](../resources/agents/11-tablegpt-agent/bindings/bridge.py) | Sandbox, date and parent ID; current text boundary does not translate attachments. |
| [33 Open Notebook](../resources/agents/33-open-notebook/bindings/bridge.py) | Async service/session bootstrap and owned process cleanup. |
| [34 AI Data Science Team](../resources/agents/34-ai-data-science-team/bindings/bridge.py) | Fixed CSV, public `invoke_agent` and response retrieval. |
| [35 Local Deep Research](../resources/agents/35-local-deep-research/bindings/ldr_bridge.py) | Settings snapshot and main-thread native API restriction. |
| [37 Article Explainer](../resources/agents/37-article-explainer/bindings/bridge.py) | Strict current-message input; implementation enables a checkpoint although its descriptive text says otherwise. |
| [38 GPT Researcher](../resources/agents/38-gpt-researcher/bindings/gpt_researcher_bridge.py) | Complete task with `publish_formats` and async research graph. |
| [39 TradingAgents](../resources/agents/39-tradingagents/bindings/tradingagents_bridge.py) | Explicit ticker/date parsing and config context around a public lifecycle. |
| [48 EvoScientist](../resources/agents/48-evoscientist/bindings/bridge.py) | Workspace setup and explicit unattended deployment configuration. |

## Review and validate

Document the exact native entrypoint, accepted input example, config/context handling, return fields, native errors, session behavior and owned resources. Keep `requirement.md` aligned with the deployed boundary: a text-only wrapper does not gain file upload just because the upstream UI supports it. Describe deployment choices such as fixed data, disabled human interaction or bounded research budgets explicitly and obtain missing choices through onboarding answers.

From the repository root with the ABB environment and KUMA validation dependencies installed, run this offline check after replacing the unit path:

```python
from pathlib import Path
from agentbench.onboarding.build_agent_env.common.validation import validate_unit
from agentbench.sdk.plugin.kuma.plugin import plugin

print(validate_unit(Path("resources/agents/NN-name"), plugin))
```

Static checks examine configuration, binding syntax/factory, supported detectable input mismatches, Docker declarations and the SDK profile. They do not prove the native import works, every branch forwards config, resources clean up correctly or the model/tool workflow completes. Without an SDK catalog context, this call does not verify selection against the live strategy catalog.

For an integration check, enable the Agent in the registry and use the verified CLI commands:

```bash
agentbench evaluate AGENT_ID --cases 1 --sdk local --no-view
agentbench evaluate AGENT_ID --cases 1 --sdk kuma --no-view
```

The local SDK uses generic text Cases and a local Judge. KUMA uses its configured service. Both can call a paid target model, and a generic Case may be unsuitable for a strict native problem format; retain a representative valid input for the binding's own invocation check. Preserve the input, actual output and traces when checking config propagation. If the application is conversational, check two Inputs in the same Case and isolation from another Case; if it is stateless, verify that its intended behavior stays stateless. Check native failure propagation and owned cleanup with the relevant resources.

Report static validation, real execution and Judge findings separately. See the [addition guide](How%20To%20Add%20Agent.md) for certification and result viewing.

## Implementation references

- [Adapter configuration](../agentbench/adapter/langgraph/config.py), [loader](../agentbench/adapter/langgraph/loader.py) and [invocation](../agentbench/adapter/langgraph/adapter.py).
- [Worker invocation](../agentbench/runtime/agentcontainer/worker.py) and [Case resource ownership](../agentbench/runtime/agentcontainer/session.py).
- [Binding generation instructions](../agentbench/onboarding/build_agent_env/frameworks/langgraph/assets/bindings/prompt.md) and [static validation](../agentbench/onboarding/build_agent_env/frameworks/langgraph/binding_validation.py).
- [KUMA onboarding requirements](../agentbench/sdk/plugin/kuma/onboarding.py) and [Docker binding layout validation](../agentbench/onboarding/build_agent_env/build_dockerfile/binding_layout.py).
