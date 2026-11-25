---
agent_description: |
  Thunderbolt's native terminal coding agent served through its own stdio ACP
  entry point. Native prompts, model resolution, skills and workspace tools remain.
input_type: text
---

## Production Use Scenario

A caller sends text to the native coding assistant in an isolated workspace.
The native ACP server manages sessions and streams responses from the Pi harness.

## Behaviors to Test

- Answer text requests and inspect supplied workspace files.
- Retain native read/write/edit, webfetch and available skill tools with native
  permission handling. Workspace jail rules determine whether bash is available.
- Propagate real provider/tool errors and respect denied permission requests.

## Known Limitations or Prohibited Behaviors

No Thunderbolt cloud account, personal files, paired remote device or MCP server
is provided. The model uses the native OpenAI-compatible provider profile populated
from ABB runtime settings. ACP client permission policy denies permission requests;
no yolo flag or relaxed workspace jail is enabled. Do not claim full desktop UI,
cloud synchronization, confidential model attestation or external account access.
