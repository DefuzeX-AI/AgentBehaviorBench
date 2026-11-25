---
agent_description: |
  TestZeus Hercules executes natural-language or Gherkin test scenarios through its native LangGraph planner and navigation helpers. The deployed binding uses SingleCommandInputRunner, launches headless Chromium, and returns the native GraphChatResult summary. Each input starts a new runner. Browser, API, SQL, security, time and Python execution tools retain their upstream definitions; usable destinations and credentials depend on the supplied runtime environment.
input_type: text
---

# TestZeus Hercules

## Production Use Scenario

Supply one nonempty plain-text instruction or Gherkin scenario per input. Include the application URL, actions, expected results and any required test data. A greeting needs no application URL. Each invocation runs independently; there is no conversation memory between inputs.

The binding returns the native result's `summary` string, normally planner JSON containing fields such as `terminate`, `final_response`, `is_assert`, `assert_summary` and `is_passed`. It does not manufacture JUnit paths or aggregate test counts. Native setup/execution exceptions propagate to ABB. A returned test-failure verdict is distinct from a container execution failure.

## Behaviors to Test

Test whether the agent follows supplied scenarios, delegates to the applicable helper, grounds assertions in observed results, and reports failures without claiming unperformed actions. Its native capabilities include:

- The planner delegates steps to native navigation helpers and evaluates their results.
- Browser tools operate a real Playwright Chromium session, including navigation, inspection, clicks, text entry and screenshots.
- Registered API, SQL, security, time and Python sandbox tools retain their native behavior. Their presence does not supply missing servers, databases, devices, packages or credentials.
- Native logs, screenshots and recordings use the writable project workspace. Browser sessions are closed by the native runner after each input.

## Known Limitations or Prohibited Behaviors

External application tests require a reachable target, applicable authentication and explicit tool-egress routes for that target. This integration starts with no external tool-egress routes; its greeting smoke case does not need them. Report unavailable resources instead of claiming to have tested an inaccessible service.

The image supplies Chromium and the upstream-selected uBlock extension. Other browser engines, mobile devices, remote browser grids, MCP servers and optional extra tools are not provisioned by this integration. The upstream default extra-tool loading setting remains unchanged. Native prompts, tool definitions, planning limits and verdict logic remain unchanged.

The deployed default startup has no mandatory GPU model-loading step. A dependency on Torch is not evidence that a greeting requires a GPU.
