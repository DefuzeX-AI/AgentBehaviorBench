# Pi coding agent ACP deployment

This unit installs the pinned [Pi](https://github.com/Dicklesworthstone/pi_agent_rust)
release `0.8.0` (tag `v0.8.0`, source commit `43ca4c0b`) from its signed GitHub
release and runs the built-in ACP server (`pi --acp`). ABB drives it over ACP
stdio and keeps each Case in a separate empty workspace. No upstream source is
vendored or modified; the image downloads the release asset and verifies it
against the release's own `pi-linux-amd64.tar.xz.sha256`.

License: **not OSI.** Upstream `LICENSE` is MIT plus an "OpenAI / Anthropic
rider" that names those companies, their affiliates and anyone acting for them as
restricted parties. This unit installs the release at image build time and does
not redistribute it; whether such an upstream is acceptable for inclusion is a
repository policy decision.

This unit uses default model selection; no `[model]` declaration is needed.
Configure the selected provider in `.env`: OpenRouter -> DeepSeek -> GLM, choosing
the first nonempty API key, or set `ABB_MODEL_PROVIDER` explicitly. Supply the
selected provider's model name as well. See
[model selection](../../../docs/Model-Selection.md) for variables and constraints.

ABB passes the resolved configuration through internal `ABB_AGENT_MODEL_API_KEY`,
`ABB_AGENT_MODEL_BASE_URL`, `ABB_AGENT_MODEL` and `ABB_AGENT_MODEL_PROVIDER`
variables. Users do not fill these internal variables.

## Installation

`install/release.json` records the pinned release: asset name, URL, size, sha256
and the licence note. The `Dockerfile` pins the same version and digest as build
arguments, so a changed upstream asset fails the build instead of silently
installing something else.

## Launcher behavior

`bootstrap/launch.py` writes one custom provider and then hands stdio to Pi:

1. `~/.pi/agent/models.json` gets a provider `abb` with `api: "openai-completions"`,
   the runtime `baseUrl`, and one model whose id is `ABB_AGENT_MODEL`;
2. the provider's `apiKey` is the *name* of an environment variable
   (`ABB_PI_MODEL_KEY`), which Pi resolves at request time, so the key is never
   written to disk;
3. `exec pi --acp --provider abb --model <model>` replaces the launcher process.

## Scope of the deployed assistant

Only the essential tool set is active: `read`, `write`, `edit`, `bash`, `grep`,
`find`, `ls`, `hashline_edit`, `ask`, `todo`, `web_search`, `submit_plan`,
`current_time`. The extension host, browser/computer/media tools, subagents, MCP
connectors and session persistence are not configured in ACP mode, so a Case sees
one agent with local file and shell tools rooted at the workspace.

## Validation scope

A local Case (`--sdk local`, Docker) checks the ACP handshake, intercepted model
traffic and recorded tool calls. File contents are not snapshotted by the local
SDK (`file-evidence.json` is produced by the KUMA runner only), so a local run
does not carry filesystem evidence.
