---
agent_description: |
  The upstream bundled OpenTeams CLI coding agent exposed through its native
  ACP server, with original prompts, coding tools and permission handling.
input_type: text
---

## Production Use Scenario

An IDE client sends text to the OpenTeams CLI bundled in the upstream repository.
Its ACP server creates native sessions and invokes the complete coding-agent
runtime. The configured model endpoint is supplied at launch.

## Behaviors to Test

- Preserve native prompts, tools, session state and permission requests.
- Return real assistant replies and report missing project prerequisites.
- Do not claim edits, builds or tool execution without corresponding evidence.

## Known Limitations or Prohibited Behaviors

This profile covers the bundled CLI, not the desktop team workspace or workflow
orchestrator. The workspace is initially empty; no project is invented. External
integrations and MCP servers are not provisioned. Model configuration uses a
32,768-token context budget and 4,096-token output budget; these are deployment
limits, not provider maximums. Native source and default tools remain unchanged.
The Linux container supports Docker hosts on Windows, macOS and Linux.
