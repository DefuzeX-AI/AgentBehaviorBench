# Mini-Agent ACP deployment

This unit runs [MiniMax-AI/Mini-Agent](https://github.com/MiniMax-AI/Mini-Agent) at commit
`d76a4f6389688cabda39c224a6cdfa274215d47c` through its own ACP stdio server
(`mini_agent/acp/__init__.py`, console script `mini-agent-acp`). ABB invokes it over ACP
and keeps each Case in a separate empty workspace. Agent code, tools and the ACP turn loop
are unchanged; the launcher-side shims below are the only behavioral adaptation.

## Source and licence

`[source] method = "git"` restores the pinned commit. The repository carries a stale
`.gitmodules` entry for `mini_agent/skills`, but at this commit the skills are ordinary
tracked files (no gitlink), so pinned Git restoration applies. Mini-Agent is MIT
(`LICENSE`); the bundled skills keep their own notices (`mini_agent/skills/THIRD_PARTY_NOTICES.md`).

## Installation

The Dockerfile exports the upstream `uv.lock` (no dev group, without the project) to a
hash-pinned requirements file and installs it with `pip --require-hashes --no-deps` from
PyPI into `/opt/mini-agent`, then installs the pinned source itself without dependencies.
The lock records a PyPI mirror's wheel URLs; exporting keeps the locked versions and
hashes while downloading from PyPI. ABB's worker uses the separate `/opt/venv`, so the
locked `agent-client-protocol==0.6.3` of the Agent and the adapter's 0.12.1 do not mix.
`uv` stays on PATH because Mini-Agent's system prompt directs Python work through `uv`.
`read_file` counts tokens with tiktoken's `cl100k_base`, which tiktoken downloads from
`openaipublic.blob.core.windows.net` on first use; that host is not admitted, so the build
caches the (hash-verified) encoding in `/opt/mini-agent-tiktoken` and the launcher sets
`TIKTOKEN_CACHE_DIR`. Without it every `read_file` call fails with the refused download.

## Model provider

This unit uses default model selection; no `[model]` declaration is needed. Configure the
selected provider in `.env` (OpenRouter -> DeepSeek -> GLM, or `ABB_MODEL_PROVIDER`). See
[model selection](../../../docs/Model-Selection.md).

`bootstrap/launch.py` maps `ABB_AGENT_MODEL_API_KEY`, `ABB_AGENT_MODEL_BASE_URL` and
`ABB_AGENT_MODEL` onto the setup that upstream's `scripts/setup-config.sh` documents: it
creates `~/.mini-agent/config/` in a disposable per-Case `HOME` with `config.yaml` (the
pinned `config-example.yaml` values, with `provider: openai`, the selected base URL used
as-is, the model and the key), plus the pinned `mcp-example.json` as `mcp.json` (every
server disabled) and `system_prompt.md`. Mini-Agent reads `api_key` only from
`config.yaml`, so that file is created with mode 0600 inside the per-Case `HOME`; the key
is removed from the Agent process environment. Requests go to
`<base_url>/chat/completions`, the exact route the runtime derives.

## Launcher compatibility shims

`bootstrap/acp_server.py` runs upstream `mini_agent.acp.main()` with two adjustments:

1. Upstream `run_acp_server` constructs `LLMClient` without `provider`, so the ACP path
   always uses the Anthropic Messages protocol and ignores `provider` in `config.yaml`,
   unlike the CLI (`cli.py`, which passes the configured provider). The shim applies the
   CLI's mapping to the ACP server's `LLMClient`. Without it the shared OpenAI-compatible
   profile cannot be used over ACP.
2. Tool loading at startup and in every `session/new` `print`s status lines to stdout,
   the JSON-RPC channel. Python-level stdout is redirected to stderr and only the ACP
   stream writer is bound to the original stdout pipe.

A native MiniMax deployment (upstream's default Anthropic endpoint with a
`MINIMAX_API_KEY`) would not need shim 1; it is not provided here.

## Behavior notes

- Tools: `read_file`, `write_file`, `edit_file`, `bash` (foreground timeout default 120 s,
  max 600 s), `bash_output`, `bash_kill`, `record_note` / `recall_notes` (stored in the
  workspace as `.agent_memory.json`) and `get_skill` for the bundled skills. No MCP server
  is enabled.
- The ACP server never sends `session/request_permission`; `allow_once` has no effect.
- Each ACP prompt runs up to `max_steps` (100) model turns; history is kept in memory for
  the session and is not summarized on the ACP path.
- Upstream's ACP path appends the skills metadata to the system prompt but leaves its
  `{SKILLS_METADATA}` placeholder in place; this is preserved.
