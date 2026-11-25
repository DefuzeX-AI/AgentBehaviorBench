---
agent_description: |
  LangAlpha's native PTC LangGraph agent with its shipped prompt, subagents,
  middleware and tools, connected to a real SSH computer inside the run container.
input_type: text
---

## Production Use Scenario

A caller sends text to the standalone PTC agent. Its native SSH provider creates
an actual local computer workspace and installs the upstream sandbox runtime.
The deployment pins the ephemeral SSH host key and uses key authentication.

## Behaviors to Test

- Respond using the native analyst prompt and tool selection.
- Preserve native file, code execution, MCP discovery, research and subagent tools.
- Report actual dependency, service and tool failures without invented results.

## Known Limitations or Prohibited Behaviors

No user portfolio, authenticated server identity, cloud sandbox account, paid
market-data subscription, search credential or storage account is supplied.
Identity-gated memory and account actions retain their upstream restrictions.
External services may reject requests without their credentials. The SSH
computer is an ephemeral container environment, not the user's host machine.
Only model clients and deployment settings are configured by the integration;
native prompts, middleware, tool implementations and access gates are retained.
