# Generate one BBA binding

Generate the complete Python file identified by `target_path`. Read the supplied
source in `context.files` and the saved `agent.toml` in `completed_files`. The
examples appended below explain the actual loader contract and show complete
bindings. Use only APIs confirmed by the TARGET repository, not imports or
deployment settings copied blindly from an example.

## What this file does

A binding connects BBA's invocation interface to the original Agent's public
execution interface. It owns necessary input/output translation and resource
lifecycle. Reasoning, tools and business logic remain in the original Agent.
Installing dependencies, granting network access and providing credentials belong
to other configuration files; a binding alone does not make an Agent runnable.

If the native exported graph already accepts the intended input and returns the
needed result, generate a minimal forwarding factory returning it (example 01).
Every generated integration requires this binding; do not silently remove it
or change agent.toml. If the requested adaptation contradicts the saved manifest
or requires missing source, return `needs_input` with the exact conflict.

## Files and names: a complete mapping

For the following illustrative layout:

```text
unit/
  agent.toml
  agent/
    langgraph.json
    src/example_agent/graph.py
  bindings/
    bridge.py
```

The relevant TOML table is:

```toml
[adapter]
type = "langgraph"
mode = "in_process"
config = "langgraph.json"
graph_id = "agent"
binding = "bridge.py:create_graph"
```

The corresponding source `agent/langgraph.json` must already declare the graph:

```json
{"graphs": {"agent": "./src/example_agent/graph.py:graph"}}
```

`target_path` is `bindings/bridge.py`; `binding` is relative to `bindings/`, so do
not put `bindings/` in that TOML value. Export `create_graph` from bridge.py.
Names above are illustrative: use the exact names in the supplied manifest.
Even with a binding, the current configuration reader still requires the source
graph JSON and graph ID. Do not invent a missing source config or edit upstream.

## Required Python interface

| Element | Input | Output / behavior |
| --- | --- | --- |
| `def create_graph()` | No arguments, including no required keyword arguments | A binding/graph object with callable `invoke`. This is a synchronous factory, not an async factory. |
| `def invoke(self, value, config=None)` | Prepared Case input; LangChain RunnableConfig or None | Actual native result, or the documented output mapping. Required even for async Agents. |
| `async def ainvoke(self, value, config=None)` | Same input and config | Awaited native result. Implement when the native execution is asynchronous. |
| Optional keyword-only `context=None` | Deployment values from `[adapter.context]` | Forward/convert only if supported by the native API. This is NOT `config['configurable']`. |
| `close()` / `aclose()` | No arguments | Release resources owned by this instance, including on partial initialization failure. |

The generated binding must export an undecorated synchronous function selected by
`file.py:factory`. It must be callable without arguments and return an object with
callable `invoke`; never return a coroutine or generator. The runtime also supports
direct objects for existing integrations, but this generator always emits a factory.
Produce a fresh instance when the binding owns mutable state or external resources.

BBA calls `invoke(value, config=run_config)` or awaits
`ainvoke(value, config=run_config)`. If no `ainvoke` exists, its async adapter runs
`invoke` in a thread. An `asyncio.run()` sync bridge is for callers WITHOUT an
active event loop; async callers must await `ainvoke`. Do not use `asyncio.run()`
inside `ainvoke`, or assume loop-bound clients survive repeated new event loops.

ainvoke MUST be a coroutine returning the final value, NEVER an async generator
yielding events. If the native public method is an async generator, consume it
inside ainvoke and return its documented final result. Check each native argument:
a method's `thread`/`config` parameter is NOT the business input. If the public
workflow gets business inputs in its constructor, construct it for the invocation
with those actual inputs, then forward RunnableConfig to its run method. Do not
create it with empty inputs and pass the input dictionary as thread configuration.

## Inputs, outputs and observation

- A mapping input passes through BBA unchanged. `input_key="message"` wraps only
  non-mapping inputs: `"hello"` becomes `{"message": "hello"}`. The binding must
  validate the actual expected shape. Do not discard unknown fields silently.
- Convert only the boundary format: example 02 converts current message text to
  the native `messages` list. Do not synthesize previous conversations, memory,
  answers, tool results, or missing required business arguments.
- Return the actual result. If TOML has `output_key="answer"`, the returned mapping
  MUST contain `answer`; returning a string or only `messages` is incompatible.
  BBA retains the raw return value and extracts the configured public output.
- Forward `config` to the native graph so callbacks, tags, metadata and thread
  settings survive. Never replace it with `{}` or serialize callback objects.
  If the public API has no config argument, use only a verified framework context
  mechanism (example 03), or explain the unsupported observation boundary.
- Do not add an OTel exporter or manufacture trace spans/results just to make
  tracing look successful. Preserving callbacks does not prove full coverage.
- Preserve exceptions as failures; never catch an execution error and return a
  success-looking answer. Error messages must not expose credentials.
- Preserve explicit completion checks from the native application as well. If its
  caller declares a missing/empty report a failed job, the binding must raise for
  that same condition. Returning partial state merely because nodes did not raise
  silently changes the application's success semantics. Do not invent additional
  quality criteria; use the actual caller's completion condition.

## Execute the complete native workflow

Identify the public method used by the upstream CLI/application, not merely the
first graph object found in a file. Some public methods perform setup, research,
report writing, cleanup or postprocessing around the graph. Omitting those steps
changes what is tested. Examples 03 and 04 demonstrate public lifecycle calls.

For resources, prefer native configuration of writable locations to rewriting
Agent code. Temporary files belong in a container-writable location, not beside
read-only source. A binding's private temporary directory is NOT a persistent
benchmark artifact directory. Close only owned resources, and make cleanup safe
to repeat. Keep original model/tool/provider choices unless supplied deployment
configuration explicitly selects otherwise. Do not copy the examples' provider
choices, feature exclusions, memory settings or concurrency assumptions wholesale.
Do not add memory or multi-turn behavior as part of this generation request.

## Explain the generated module for a human maintainer

Include a module docstring describing the native entrypoint and adaptations.
Document the factory and invocation methods with input shapes, config/context,
return fields, raised errors and resource ownership. Include one concrete input
example in a docstring. Output examples must describe shape, not fabricate a
model answer. Use complete implementations: no TODO bodies, `...`, mock Agents,
hardcoded responses, shell launches, or dependency installation in the binding.

## Response format

Return a JSON object matching the supplied schema, without a Markdown wrapper.
This is a structural example; replace every explanatory value:

```json
{
  "status": "complete",
  "summary": "Explain the native call, input/output translation and owned resources.",
  "evidence": ["EXACT_PATH_FROM_CONTEXT_FILES"],
  "missing_information": [],
  "path": "bindings/bridge.py",
  "content": "FULL_PYTHON_SOURCE_WITH_NEWLINES"
}
```

`path` must equal this request's `target_path`. `content` is the entire file as a
JSON string, not a fenced code block. Evidence paths must exist in this request.
For `needs_input`, retain the same path, set content to an empty string, and list
concrete missing source/API details or conflicts in `missing_information`.
Do not claim static validation establishes successful installation or execution.
