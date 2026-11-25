---
agent_description: |
  Aix-DB's native EnhancedCommonAgent using its original DeepAgents loop,
  built-in skills, local shell tools, prompt memory and SSE response stream.
input_type: text
---

## Production Use Scenario

A caller sends a message to the native enhanced general assistant. A disposable
PostgreSQL database stores a real locally registered user, the configured model
and conversation records. Native authentication issues the session token.

## Behaviors to Test

- Preserve built-in skills and file, shell, planning and ask-user tools.
- Respond to text without inventing data or claiming unavailable connections.
- Return native SSE events and report native errors as failed execution.

## Known Limitations or Prohibited Behaviors

No business datasource, uploaded document, remote MCP hub or object-storage
account is supplied. Native optional-MCP handling remains unchanged; no empty
fake MCP service is provided. Do not claim database analysis or uploaded-file
access without the required real input. Model settings are stored in the native
model table; native prompts, tools, skills and access checks remain unchanged.
