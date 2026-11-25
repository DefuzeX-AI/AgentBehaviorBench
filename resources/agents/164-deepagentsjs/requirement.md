---
agent_description: |
  The upstream DeepAgents JavaScript ACP CLI, built from its pinned workspace,
  with the native coding-agent prompt, planning, filesystem and delegation tools.
input_type: text
---

## Production Use Scenario

An ACP client sends text to the native deepagents-acp coding assistant. The CLI
uses its normal filesystem backend rooted at the disposable workspace.

## Behaviors to Test

- Answer through the native ACP session and DeepAgents execution loop.
- Preserve native filesystem, planning, subagent and permission behavior.
- Report real file, model and tool errors without fabricated success.

## Known Limitations or Prohibited Behaviors

No user repository, custom skill pack, memory file, remote MCP service or cloud
sandbox account is supplied. No project contents or successful edits may be
invented. The ACP client denies permission requests that require approval.
Only the native CLI's model option and model endpoint environment are configured;
the native prompt, tool set and middleware are unchanged.
