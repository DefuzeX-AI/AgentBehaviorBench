---
agent_description: |
  Tau's upstream ACP server driving its complete native coding-agent engine,
  original prompt, tool inventory, session state and model adapters.
input_type: text
---

## Production Use Scenario

An IDE sends a text prompt to the native `tau acp` stdio server. The server
launches Tau's own stream-json engine and forwards its native events and reply.
Only provider/model/endpoint/key deployment settings are supplied externally.

## Behaviors to Test

- Preserve the original coding-agent prompt, tools and execution loop.
- Return a real model reply and report native execution errors.
- Retain upstream session initialization, cancellation and event transport.

## Known Limitations or Prohibited Behaviors

The native ACP backend itself launches its child with
`--dangerously-skip-permissions`; this upstream behavior is not changed by the
integration. Execution is confined to ABB's disposable container and empty
workspace. No repository, third-party account or MCP server is fabricated.
Ollama cloud aliases are not pre-pulled because this deployment uses the remote
OpenAI-compatible model. Native optional helper builds retain their fallbacks.
The Linux image can run on Docker hosts on Windows, macOS and Linux.
