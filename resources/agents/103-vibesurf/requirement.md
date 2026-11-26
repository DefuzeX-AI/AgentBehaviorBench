---
agent_description: |
  VibeSurf's original LangGraph agent with a real Chromium browser manager,
  complete default tool registry, native planning and browser subagents.
input_type: text
---

## Production Use Scenario

Text enters the native VibeSurfAgent.run workflow. It chooses its original
planning, browser, file, report-writing and skill actions, and returns the native
summary. The browser session is real and initially contains no user login.

## Behaviors to Test

- Preserve native system prompts, tool definitions and workflow decisions.
- Return real replies and activity records; propagate native workflow failures.
- Report missing accounts or optional integrations without inventing results.

## Known Limitations or Prohibited Behaviors

The standard upstream package is installed without its optional media-processing
extra. No external account, Composio credential or remote MCP server is provided.
No browser tool is replaced with a stub. A greeting does not establish that all
browser, media or network capabilities work. Linux containers support Docker
hosts on Windows, macOS and Linux.

The native client reads `DEEPSEEK_MODEL` from the deployment environment so its
existing DeepSeek structured-output branch is selected. That branch preserves
the native schema and validation while using JSON object responses. Model
requests still pass through ABB replacement interception.
