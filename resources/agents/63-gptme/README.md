# gptme ACP deployment

This unit installs the pinned [gptme](https://github.com/gptme/gptme) release
`0.35.1` (PyPI `gptme[acp]`; tag `v0.35.1`, commit `0c131bb0`, MIT license) and
runs its built-in ACP server (`gptme-acp`, `gptme/acp/__main__.py`). ABB invokes it
over ACP stdio and keeps each Case in a separate empty workspace. No upstream
source is vendored or modified.

This unit uses default model selection; no `[model]` declaration is needed. Configure the selected provider in
`.env`: OpenRouter -> DeepSeek -> GLM, choosing the first nonempty API key, or set
`ABB_MODEL_PROVIDER` explicitly. Supply the selected provider's model name as well.
See [model selection](../../../docs/Model-Selection.md) for variables and constraints.

ABB passes the resolved configuration through internal `ABB_AGENT_MODEL_API_KEY`,
`ABB_AGENT_MODEL_BASE_URL`, `ABB_AGENT_MODEL` and `ABB_AGENT_MODEL_PROVIDER` variables.
Users do not fill these internal variables. Only the selected credential reaches the
launcher. The runtime derives the exact observed model route from the selected URL.

The runtime admits the exact `POST <selected-base>/chat/completions` route.

## Installation

`install/requirements.txt` is a fully pinned, `--require-hashes` lock of the
`gptme[acp]==0.35.1` closure (including `agent-client-protocol==0.12.1`), generated
from `install/requirements.in` with `uv pip compile --universal --generate-hashes`
for CPython 3.12, so the same lock installs on x86_64 and aarch64 hosts. The image
is based on `python:3.12-bookworm` (upstream supports Python 3.10-3.14). gptme
lives in its own venv `/opt/agent-venv`; ABB's runtime dependencies stay in
`/opt/venv`. Debian's `ripgrep` is installed for shell searches.

tiktoken downloads its BPE files from `openaipublic.blob.core.windows.net` on first
use, which the interceptor would refuse. The image therefore caches `cl100k_base`
(used for model names tiktoken does not know) and `o200k_base` at build time under
`/opt/tiktoken-cache`, and the launcher sets `TIKTOKEN_CACHE_DIR` to it (the ACP
worker does not pass image `ENV` to the Agent process), so token counting keeps
upstream behavior without a runtime download.

## Launcher behavior

`bootstrap/launch.py` validates the three variables (HTTPS base URL without query
or fragment), creates a disposable per-Case `HOME` under `/tmp` with XDG
directories inside it, and execs `/opt/agent-venv/bin/gptme-acp`. The disposable
`HOME` keeps gptme's `~/.config/gptme`, conversation logs and state writable by
whichever unprivileged uid the runtime chooses and isolates Cases: memories,
lessons state and past chats never carry over between Cases.

- gptme's documented route for any OpenAI-compatible Chat Completions server is
  its `local` provider. The launcher sets `OPENAI_BASE_URL` to
  `ABB_AGENT_MODEL_BASE_URL`, `OPENAI_API_KEY` to the selected credential and
  `GPTME_MODEL=local/$ABB_AGENT_MODEL`. The key stays in the environment and never
  appears in argv or on disk. `GPTME_MODEL` outranks every config-file `MODEL`
  setting; ACP `session/new` does not choose a model.
- It drops inherited `OPENAI_API_BASE` (which the `local` provider prefers over
  `OPENAI_BASE_URL`) and `LLM_PROXY_URL` / `LLM_PROXY_API_KEY`, which would
  re-point requests away from the selected endpoint.

gptme runs its tools itself inside the container and workspace; it does not
delegate to ACP `fs/*` or `terminal/*`. In 0.35.1 its ACP server registers no
confirmation hook, so tools run without ACP `session/request_permission`, and it
sends no ACP `tool_call` updates: each command's or file operation's result is
forwarded as `agent_message_chunk` text after the turn's streamed assistant text.
`permission_policy = "allow_once"` therefore never fires; tool activity is
evidenced by the intercepted model traffic (each tool result is sent back to the
model), the forwarded tool-result text and workspace file evidence. Upstream ACP
fixes the tool format to markdown code blocks, so model requests carry no `tools`
parameter. gptme telemetry stays off (it requires `GPTME_TELEMETRY_ENABLED` and the
`telemetry` extra, neither of which is set).

## Tools

The default tool set loaded in this image is `shell`, `ipython`, `save`, `append`,
`patch`, `patch_many`, `todo`, `memory`, `chats`, `lessons`, `recall`, `convert`,
`vision`, `mcp`, `autocommit`, `autocompact` and `vent`. Upstream marks `browser`,
`gh`, `tmux`, `rag`, `screenshot`, `precommit` and `morph` unavailable here because
their binaries, packages or keys are absent; they are not installed to keep the
deployment to the declared model route. No MCP server is configured.

## Web access

There is no web tool. Requests the Agent makes from its shell or Python tools go
to ABB's egress observer, which forwards allowlisted hosts (the package registries
by default), refuses the rest with 403 and records every attempt in
`egress.jsonl`; a refusal does not reject the Case (#137).

## Installation inputs

Tracked installation manifests live in install/. Before the evaluation SDK starts, ABB prepares their copies in the ignored agent/ directory (source.method = install). Docker builds use those generated copies. Do not edit agent/; edit install/ instead. If an existing copy differs, move agent/ aside and rerun to regenerate it.

## Validation scope

Acceptance records describe the provider/model combination they name. They do not
certify every shared provider/model combination; run a fresh Case after changing it.
