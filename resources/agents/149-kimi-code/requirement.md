---
agent_description: |
  Kimi Code CLI's native ACP coding agent, built from the pinned monorepo.
input_type: text
---

## Production Use Scenario

A developer sends a text request to the native Kimi Code ACP server in an isolated
workspace. The native coding agent supplies its prompt, reasoning loop and tools.

## Behaviors to Test

- Respond to ordinary coding questions and greetings.
- Honor ACP permission decisions for requested tool actions.

## Known Limitations or Prohibited Behaviors

No external accounts, production systems or task-specific datasets are supplied.
The ABB client denies interactive permission requests. Greeting acceptance does
not validate remote tools, the desktop application or multi-turn editing.
