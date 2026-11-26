---
agent_description: |
  Pizza Bot's original stateful DeepAgents/LangGraph runtime served by its real
  API backend, with default skills, plugins, memory and human approval gates.
input_type: text
---

## Production Use Scenario

The caller submits text through the same native protocol client used by the
terminal CLI. The actual backend owns agent assembly, original system prompts,
SQLite checkpoints, plugins, skill delegation and its complete run manager.

## Behaviors to Test

- Preserve native skills, tool dispatch, streamed events and persistent state.
- Report human approval requirements without granting an invented decision.
- Return a genuine completed reply and propagate native run errors.

## Known Limitations or Prohibited Behaviors

No external account or user folder grant is configured. Native plugins requiring
these prerequisites must report their absence. Chromium is installed but a
greeting alone does not validate browser execution. Only model settings and local
deployment authentication are supplied; original prompts and tools are retained.
Linux containers support Docker deployment on Windows, macOS and Linux hosts.
