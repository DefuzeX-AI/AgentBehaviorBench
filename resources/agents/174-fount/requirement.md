---
agent_description: |
  fount's built-in ZL-31 character through its native IDE integration ACP service,
  retaining the original character prompt, plugin set and reply pipeline.
input_type: text
---

## Production Use Scenario

An IDE client connects to a real local fount deployment using the upstream ACP
stdio client. Normal registration and login create an ephemeral local account;
the native service manager configures its model source. ZL-31 receives the text
through the original ACP and character interfaces.

## Behaviors to Test

- Preserve the native character prompt and its complete default plugin selection.
- Preserve native tool execution, permission requests, failures and reply history.
- Return a real model-backed reply, not a built-in introductory message.

## Known Limitations or Prohibited Behaviors

No external browser session, user data, social account or paid search service is
provided. Dependent capabilities must report missing prerequisites. The greeting
does not validate every plugin. Native prompts, tool loops and source remain
unchanged. The upstream runtime uses unlocked Deno dependencies. Linux containers
support deployment on Windows, macOS and Linux Docker hosts.
