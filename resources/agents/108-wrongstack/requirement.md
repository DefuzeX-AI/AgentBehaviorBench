---
agent_description: |
  WrongStack's native ACP coding-agent server, retaining its original leader
  prompt, provider adapter, tools, policy, memory and delegation runtime.
input_type: text
---

## Production Use Scenario

An editor client starts `wstack acp` and sends a text task through ACP stdio.
The native server boots the real runtime and creates a normal coding session.
Deployment environment variables select its model endpoint and credentials.

## Behaviors to Test

- Preserve original prompts, tools, Brain policy, memory and native agent loop.
- Return the real response and native tool events through ACP.
- Retain native permission requests and cancellation semantics.

## Known Limitations or Prohibited Behaviors

No cloud account, project repository, remote worker or MCP service is fabricated.
The workspace begins empty. Only provider/model/base URL/key settings are changed.
The normal CLI ACP server is used, never its `--echo` connectivity mode.
The Linux image supports Docker hosts on Windows, macOS and Linux.
