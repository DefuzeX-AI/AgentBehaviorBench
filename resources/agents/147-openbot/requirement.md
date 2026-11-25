---
agent_description: |
  OpenBot's upstream Python LangGraph AG-UI Bot, using its native answer/tools graph
  and ToolAwareAgent run lifecycle. This standalone deployment accepts text.
input_type: text
---

## Production Use Scenario

A caller sends a text message to the native LangGraph Bot and receives its AG-UI
response events. The deployment retains native model selection and error handling.

## Behaviors to Test

- Answer ordinary text questions using the conversation supplied by the caller.
- Propagate provider failures instead of reporting a fabricated successful answer.

## Known Limitations or Prohibited Behaviors

The OpenBot organization server and user-specific role/tool grants are not supplied.
The upstream AG-UI contract receives no granted tools, context or standing-role
messages for this standalone greeting. Do not claim access to a browser, external
accounts or organization tools. This validates the upstream Bot backend, not the
full OpenBot UI, authentication, organization memory or tool governance service.
