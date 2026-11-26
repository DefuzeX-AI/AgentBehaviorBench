---
agent_description: |
  WebQA native Flash browser-testing workflow with Chrome DevTools MCP.
input_type: text
---

## Production Use Scenario

Run the original CLI Flash workflow with its native prompts, browser tools and
report generation. The smoke deployment serves a real local greeting page at
127.0.0.1:8787 and forwards the user text as the native business objective.

## Behaviors to Test

Preserve the real browser, screenshots, native execution and outcome checks.
The target is an isolated local test page, not a mock browser or external site.

## Limitations

This deployment uses the native Flash mode; optional standard-engine security
scanners are not part of this smoke case. Native failures remain failures.
