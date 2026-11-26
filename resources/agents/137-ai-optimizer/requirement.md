---
agent_description: "Oracle AI Optimizer native LLM-only agent"
input_type: text
---

# Oracle AI Optimizer native LLM-only agent

This integration deploys the upstream LLM-only AgentSpec through `build_llm_only_agentspec`, `load_langgraph_component` and `AgentGraphSession.chat`. It uses the original `optimizer_basic-default` factory prompt, native model adapter, graph and session processing. This is the explicitly provided pure-conversation mode, whose native definition has no tools.

It accepts a text greeting and returns the native agent's reply. This integration does not certify the separate NL2SQL, vector retrieval or combined routes, nor the complete web server. Those platform routes require configured Oracle databases, SQLcl/MCP resources and data; none are fabricated or emulated here. The web server's mandatory CORE database startup is not invoked by this standalone AgentSpec integration.

Only model settings are configured for interception. The Docker image installs the full native server dependency set, including upstream CPU PyTorch selection, using architecture-neutral Linux build steps for Docker hosts on Windows, macOS and Linux.
