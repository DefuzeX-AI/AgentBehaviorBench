---
agent_description: |
  Janito's native ACP stdio server and its original headless agentic loop,
  shared with the web surface, including tools, skills, MCP and privileges.
input_type: text
---

## Production Use Scenario

Launch the upstream janito --acp command and send caller text through its native
ACP session rooted in an isolated workspace. Configure the native custom provider
and credential stores using Janito's own configuration APIs.

## Behaviors to Test

- Preserve native prompts, skills, tool selection and agentic execution.
- Preserve native default privileges and any approval or human-input behavior.
- Return native ACP responses, tool updates and cancellation results.

## Known Limitations or Prohibited Behaviors

No project, external MCP server, business credentials or extra privileges are
invented. Only model, endpoint, API protocol and model credentials are configured.
The native custom provider uses OpenAI-compatible chat completions with ABB's
runtime model settings. Linux containers support Windows, macOS and Linux hosts.
