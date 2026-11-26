---
agent_description: |
  SwarmClaw's native authenticated chat service with its original agent runtime,
  default tools, persistent session messages, memory and approval policies.
input_type: text
---

## Production Use Scenario

A caller sends text to an actual local SwarmClaw deployment. Its native API
creates a default agent and chat session, then enqueues the message through the
original session-run manager and streams the real response. Only model endpoint
settings and ephemeral local deployment credentials are supplied.

## Behaviors to Test

- Preserve native base prompts, default tool selection and agent execution loops.
- Preserve native approval requests, tool errors and conversation persistence.
- Return real native replies and report failures without substituting responses.

## Known Limitations or Prohibited Behaviors

No external gateway, browser Docker socket, paid connector, remote MCP service or
user data is provisioned. Tools needing these prerequisites must report their
absence. A greeting does not establish working browser or external connector
execution. No approval is automatically granted. Native source remains unchanged.
The Docker deployment runs in Linux containers on Windows, macOS and Linux hosts.
