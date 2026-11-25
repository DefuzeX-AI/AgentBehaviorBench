---
agent_description: Zed's official headless eval-cli runs its native coding agent in an isolated Linux workspace. An outer ACP bridge transports one text prompt and returns native messages and tool evidence.
input_type: text
---

## Deployment

The input is a single text prompt. The native CLI starts a fresh agent session
in `/home/agent/workspace`. The upstream agent loop, prompts and tools remain
unchanged. Filesystem, terminal and other registered native tools retain their
upstream behavior; external services and project inputs must actually be available
before their use can succeed. The container includes Python, Git, curl and ripgrep.

## Limitations

The transport supports one prompt per Case; it does not simulate multi-turn
history. Native artifacts are preserved under `.zed-evidence/`. Tool events are
reported after completion from native saved records, not as live timing evidence.
No external MCP servers or editor UI are configured. This profile supports the
native execution-only smoke case; no KUMA strategy selection or certification
is claimed.
