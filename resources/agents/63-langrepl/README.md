# langrepl

This unit loads the native default `general` graph through the asynchronous
`langrepl.cli.bootstrap.initializer.Initializer.create_graph` and awaits its
returned cleanup function. Upstream source is unmodified and restored from the
full commit recorded in `agent.toml`; package version 1.12.1 is MIT licensed.
Python 3.13 and production dependencies come from upstream's frozen `uv.lock`.
The lock's yanked NumPy 2.4.0 is deliberately preserved.

Run source preparation through ABB before building. The outer Dockerfile installs
Git, ripgrep, fd, tree and bubblewrap. ABB stages its Python worker and telemetry
dependencies; no Python 3.13 packages are installed into the host environment.

Upstream defaults select Anthropic. The binding's deployment configuration changes
the selected main agent, both subagents and configured compression model to the
native OpenAI-compatible client, retaining their generation limits. Native model
labels are set to `deepseek-v4-pro`; provider-specific reasoning/options and native
Anthropic cost estimates are cleared. Graph logic and tools are unchanged.
The manifest registers Chat Completions with ABB replacement interception,
including its nested `LLM__OPENAI_API_KEY` environment variable. The host-selected
model applies to all matching calls. This integration was prepared for Bailian's
OpenAI-compatible endpoint with `deepseek-v4-pro`; host model configuration
supplies the actual credentials, endpoint and effective model.
No provider credentials or fixed provider restriction belong in this unit.
The unit has no fixed non-model API endpoints. For web-fetch tasks, configure the
needed destinations using host `ABB_EGRESS_ALLOW`; the default observer permits
package registries rather than arbitrary websites. All traffic remains observed.

## Binding boundary

`bindings/bridge.py:create_graph` is synchronous and requires no arguments.
The returned object exposes `invoke`, `ainvoke`, `close` and `aclose`.
Async initialization is lazy. Sync callers share one persistent event loop;
async callers must invoke and close on their original event loop.

Text and `{"message": "..."}` Inputs use the native MessageContentBuilder.
Native `{"messages": [...]}` state is also accepted. An explicit structured
`{"resume": ...}` Input becomes a native LangGraph Command for a pending interrupt.
The binding forwards caller config, retaining the Case's thread ID, callbacks,
metadata and limits. SQLite history persists across Inputs in that Case.
The native context includes workspace, user memory, tool and skill catalogs,
platform/time, output limit and native cost metadata.

The output has `response` (the assistant content or an explicit pending approval
notice) and `state` (the complete native graph result). Native exceptions propagate.
Use `await graph.aclose()` in a finally block for asynchronous callers and
`graph.close()` for synchronous callers.

## Deployment limits

The native `general` graph and semi-active approval mode remain in place, with
the model configuration override described above. An interrupt is returned to
the caller without an automatic decision.
No MCP servers are configured. The graph interface does not expose the interactive
CLI, slash commands, clipboard, or CLI-managed automatic history compression.
The configured compression model would use the same Chat Completions interceptor, but this binding
does not execute the CLI's compression handler or claim compression acceptance.

Native optional sandboxing stays disabled, matching upstream. The Python 3.13
image imports `pyseccomp`, but upstream's bubblewrap backend imports `seccomp`,
which is absent. Installed bubblewrap also cannot create namespaces under the
tested standard Docker security policy. This unit does not enable privileged
Docker or weaken that policy to make optional nested sandboxing pass.
The normal default graph initializes without those optional features.

The Case workspace is initially empty at `/workspace/langrepl`; supply task facts
in text. Referenced files must already exist in the container. No host files or
credentials are implicitly mounted. `requirement.md` describes deployed behavior.

## Local smoke

From the ABB repository root, with host model credentials configured:

```sh
ABB_LOCAL_JUDGE_MAX_CHARS=1000000 ./.venv/bin/python -m agentbench evaluate langrepl \
  --cases 1 --sdk local --model deepseek-v4-pro \
  --case-file tests/agent_fixtures/issue516_cases.json --no-view -y
```

The two-turn Case exercises native todo tools and conversation history. The
supported Judge size setting allows full framework evidence to be assessed
without truncation; the default 120,000-character limit can be too small for
this graph's tool traces. Local SDK runs use the configured model quota.
The profile selects `basic-safety-general` version `1` (Basic Safety — General
Observable) for the deployed general-purpose assistant. This covers its broad
text-and-tool boundary without assuming a dedicated browser, coding or research
workflow. Catalog-backed selection validation is separate from live KUMA
evaluation; refresh availability before a future KUMA run.
