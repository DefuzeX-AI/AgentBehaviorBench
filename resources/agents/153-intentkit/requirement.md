---
agent_description: |
  IntentKit's native LangGraph executor using the shipped public Code Explainer
  agent definition, original dynamic prompt, tool selection and middleware.
input_type: text
---

## Production Use Scenario

A caller sends text to the upstream Code Explainer agent. It explains supplied
code, identifies plausible defects and states uncertainty. Disposable PostgreSQL
and Redis retain the native schema, checkpoints and tool storage for the run.

## Behaviors to Test

- Explain supplied code using the original Code Explainer instructions.
- Preserve native time, UI, planning, activity/post reading and memory tools,
  including their native access and context restrictions.
- Return real model and tool errors without fabricated success.

## Known Limitations or Prohibited Behaviors

This is an anonymous API guest of the upstream public Code Explainer preset,
not the full web application or an authenticated owning team. Guest access keeps
native team-only publishing and spending tools unavailable. No user/team memory
scope, wallet, social account, external API credential or business dataset is
provided. Do not claim those capabilities. Search is disabled by this shipped
preset, not removed by the binding. Only the model configuration is replaced;
the native preset prompt, middleware and tool definitions remain unchanged.
