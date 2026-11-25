---
agent_description: |
  LibreFang's native ACP server and in-process kernel with its automatically
  provisioned assistant, original prompt, tools, memory and approval handling.
input_type: text
---

## Production Use Scenario

Native `librefang init --quick` initializes the disposable home. `librefang acp`
boots the real kernel, selects its native default assistant and serves the IDE
protocol. Only the default model provider, endpoint, model and key setting change.

## Behaviors to Test

- Preserve native assistant provisioning, prompts, tools and memory.
- Return real model responses through the upstream ACP implementation.
- Retain native session persistence, approvals and cancellation.

## Known Limitations or Prohibited Behaviors

Registry content is obtained through the native initialization mechanism during
the image build. No paid channel account, remote browser, target system or
project data is fabricated. Rust build parallelism is bounded to fit the host.
The image builds for the selected Docker architecture and runs on Windows,
macOS and Linux Docker hosts.
