---
agent_description: |
  NexusDesk's native default customer-service runtime, accessed through its real
  authenticated run API, PostgreSQL admission and embedded execution worker.
input_type: text
---

## Production Use Scenario

Start the complete native customer-service application with an actual isolated
PostgreSQL database and upstream migrations. Submit the caller's exact text to
its run API using a locally provisioned service credential. Preserve native
runtime prompts, validation, limits, event persistence and execution behavior.

## Behaviors to Test

- Produce a native customer-service response with the configured real model.
- Preserve missing-business-data behavior and approval rules in native prompts.
- Return only completed run output; retain actual runtime errors and cancellation.

## Known Limitations or Prohibited Behaviors

This uses the upstream default runtime with no configured business HTTP tools,
external channels, knowledge documents or sample shop data. No demo model or
mock tool is enabled. No business record or customer order is invented. This
smoke run does not validate a configured industry agent or enterprise integrations.
Model settings select the native OpenAI-compatible backend with chat completions.
Linux containers support Docker hosts on Windows, macOS and Linux.
