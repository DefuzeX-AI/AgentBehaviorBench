---
agent_description: |
  MCP Client CLI is a LangGraph conversational agent with configurable MCP tool connections and built-in SQLite memory. This deployment preserves the upstream example system prompt, native model initialization, tool-loading function, save_memory tool, checkpointing and conversation-state construction. ABB supplies one text message and receives the complete final native graph state. No external MCP server is provisioned in this greeting configuration.
input_type: text
---

# MCP Client CLI

## Production Use Scenario

Supply a nonempty text message or exactly `{"message": "text"}`. The agent provides conversational assistance using the upstream software-engineering prompt. A fresh checkpoint thread is created for each input unless a thread ID is explicitly provided in RunnableConfig. SQLite memory is available within the container's lifetime; it is not a promise of durable storage across independent ABB containers.

The binding returns the complete final LangGraph state, including messages, assistant replies, tool results and native state fields. Configuration, setup and execution errors propagate instead of becoming fabricated replies.

## Behaviors to Test

- Appropriate responses to the actual user message while following the native prompt.
- Correct use of the native `save_memory` tool, which stores user memories in SQLite and is loaded through the upstream `load_tools` function.
- Faithful use of retrieved memories and accurate reporting of available capabilities.
- Native tool confirmation behavior when a user-configured MCP tool requires confirmation; the binding does not bypass that requirement.

The default configuration uses the exact `systemPrompt` from the pinned repository's example file. No external MCP servers are configured. The example fetch, Brave Search, YouTube and command-execution servers are user-supplied integration examples, not installed built-in capabilities.

## Known Limitations or Prohibited Behaviors

Do not claim web access, external search, YouTube access or shell execution from this deployment. Those require separately configured and installed MCP servers, any applicable credentials and network routes. The binding retains the native server-loading path, but does not manufacture tools or their results.

Clipboard, image input and CLI continuation/template commands are outside this text binding. The native memory tool and checkpoint database use a writable container home. No local GPU model is required by this selected configuration.
