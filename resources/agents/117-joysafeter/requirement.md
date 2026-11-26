---
agent_description: |
  JoySafeter's native DeepAgents Copilot for designing agent workflow graphs.
  Uses the complete upstream non-streaming Copilot runner and its native manager.
input_type: text
---

## Production Use Scenario

Start with an empty workflow graph and submit the user's text to the native
Copilot runner. The upstream prompt includes the actual zero-node, zero-edge
state. Its manager retains the requirements analyst, workflow architect and
validator sub-agents, native prompts and artifact handling.

## Behaviors to Test

- Answer user requests through the native manager and delegation workflow.
- Preserve create_node, connect_nodes, delete_node and update_config tools.
- Preserve native filesystem and planning tools supplied by DeepAgents.
- Return native messages, proposed graph actions and artifact locations.

## Known Limitations or Prohibited Behaviors

This entry point designs workflows; it does not execute a security assessment.
No target, existing graph, business requirements or external credentials are
invented. Proposed graph actions are returned without applying them to a live
project. Model deployment settings are supplied through ABB. A greeting does
not establish the correctness of generated workflows or external services.
Linux containers support Docker hosts on Windows, macOS and Linux.
