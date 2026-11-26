---
agent_description: |
  Atom's native personal-edition Meta-Agent, entered through its authenticated
  execute API, with its original ReAct loop, tool dispatch and audit controls.
input_type: text
---

## Production Use Scenario

A local personal-edition installation receives a natural-language request.
The native bootstrap creates its administrator and personal workspace, and
the client signs in normally before invoking the Meta-Agent. Original task
admission, governance, approvals, memory and tool behavior remain active.

## Behaviors to Test

- Answer through the full native Meta-Agent and retain its execution outcome.
- Use native tools only when authorized and configured for the local instance.
- Ask for missing task information or approvals rather than inventing them.

## Known Limitations or Prohibited Behaviors

The deployment has a fresh local database, not a user's existing business data.
External service accounts, remote devices and customer records are not supplied.
No approval or governance bypass is enabled. Native starter templates may be
seeded by the application; they are not evidence of completed business work.
The transport exposes text requests and does not automatically approve actions.
The Docker deployment runs Linux containers on hosts with Docker support.

This unit uses bundled source. Before building, supply the upstream checkout
under this unit's `agent/` directory at the repository and revision recorded in
`source-manifest.json`, including its required source assets. The inner source
directory is not distributed in this integration PR and is not auto-downloaded.
