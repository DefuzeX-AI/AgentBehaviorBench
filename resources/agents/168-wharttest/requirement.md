---
agent_description: |
  WHartTest's native authenticated Agent Loop API, using its original LangChain
  graph, middleware, prompts, tools and human approval rules.
input_type: text
---

## Production Use Scenario

A caller chats with the native testing assistant through the live Django ASGI
endpoint. A real disposable database contains a local user and an empty project;
the native JWT authentication and project permission checks are executed.
PostgreSQL runs locally with the upstream migrations and native PostgreSQL
checkpointer; the migration set contains PostgreSQL-specific JSONB SQL.

## Behaviors to Test

- Respond through the original Agent Loop endpoint and return native results.
- Preserve builtin tool selection, MCP loading, skill guards and human approval.
- Report missing application services, input data and native execution errors.

## Known Limitations or Prohibited Behaviors

No application under test, browser login, test specification, uploaded document
or user credential is supplied. No remote actuator or user-configured MCP server
is fabricated. An empty project is deployment state, not a test target or test
dataset. Do not claim successful tests or browser actions without tool evidence.
Only database/service deployment and model configuration are set by the binding.
