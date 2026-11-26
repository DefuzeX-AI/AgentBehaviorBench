---
agent_description: |
  DotCraft's native ACP bridge, AppServer and local agent runtime with its
  original prompts, built-in tools, plugins and permission handling.
input_type: text
---

## Production Use Scenario

An IDE starts `dotcraft acp`; the native bridge starts the real local AppServer
and forwards session messages to its agent. User configuration selects only
the model provider, API endpoint, key and model. The native `dotcraft setup`
command initializes the empty local workspace and its original templates before
ACP starts.

## Behaviors to Test

- Keep native prompts, plugins, tools, session state and approvals.
- Forward native replies, tool events and errors through ACP.
- Preserve native cancellation and child-server lifecycle.

## Known Limitations or Prohibited Behaviors

No project repository, remote Satellite, ChatGPT account, mobile connection or
chat-channel credentials are fabricated. Chat-channel seed bundles are not
provisioned for this local ACP session. The bundled desktop plugins are built
from the same source revision. Linux x64/ARM64 publication follows Docker's
target architecture; the image can run on Windows, macOS and Linux Docker hosts.
