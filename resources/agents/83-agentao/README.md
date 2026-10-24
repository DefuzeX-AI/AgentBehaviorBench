# Agentao ACP deployment

This unit installs the pinned [Agentao](https://github.com/jin-bo/agentao) release
`0.5.16` (PyPI `agentao[web]`; tag `v0.5.16`, commit `51d8e942`, MIT license) and
runs its built-in ACP server (`agentao --acp`). ABB invokes it over ACP stdio and
keeps each Case in a separate empty workspace. No upstream source is vendored or
modified.

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
`agentao[web]==0.5.16` closure for CPython 3.12, generated from
`install/requirements.in` with `uv pip compile --generate-hashes`. The `web` extra
adds `beautifulsoup4` so `web_fetch` can extract readable text from HTML; the CLI,
Playwright and tokenizer extras are not installed because the ACP server needs
none of them. The agent lives in its own venv `/opt/agent-venv`; ABB's runtime
dependencies stay in `/opt/venv`. Debian's `ripgrep` is installed so
`search_file_content` takes its ripgrep fast path.

## Launcher behavior

`bootstrap/launch.py` validates the three variables, then for every Case creates a
disposable `HOME` (and XDG dirs) under `/tmp`. Agentao's user directory
`~/.agentao` (login file, memory, saved sessions, logs) therefore starts empty,
stays writable by whichever unprivileged uid the runtime chooses, and is isolated
per Case. It then execs `/opt/agent-venv/bin/agentao --acp`.

- Agentao reads `LLM_PROVIDER` and then `{PROVIDER}_API_KEY`, `{PROVIDER}_BASE_URL`,
  `{PROVIDER}_MODEL` and `{PROVIDER}_API_FORMAT`. The launcher sets
  `LLM_PROVIDER=ABB` and the matching `ABB_*` block from the selected profile, with
  `ABB_API_FORMAT=openai-completions` so the client stays on Chat Completions.
  The key is passed in the environment only, never in argv or on disk.
- ACP sessions resolve LLM settings from three layers, highest first: the server's
  launch environment, the session's `<cwd>/.env`, and `~/.agentao/llm.json`. The
  launch environment names the provider and fills every field, so a `.env` the
  Agent writes into the workspace cannot re-point the model. The launcher also
  drops inherited `OPENAI_*`, `ANTHROPIC_*`, `DEEPSEEK_*`, `GEMINI_*` and `LLM_*`
  variables so no other provider block or tuning value leaks in.
- Agentao already scrubs provider keys from shell child processes by default
  (`AGENTAO_SCRUB_CHILD_ENV`), so `run_shell_command` does not see the key.

Agentao runs in its default `workspace-write` permission mode. Ordinary
`write_file`/`replace` calls and read-only shell commands are allowed directly;
destructive patterns (`rm -rf`, `sudo`, `mkfs`, `dd if=`) are denied; other shell
commands and writes to `.git/`, `.agentao/` or credential paths are sent as
`session/request_permission`, which ABB answers per `permission_policy =
"allow_once"`. Agentao's `_agentao.cn/ask_user` extension request is answered with
"method not found" by ABB's ACP client, so `ask_user` returns
`(user unavailable)` and the Agent must continue without a user.

## Network

No tool route is declared. Without `BOCHA_API_KEY`/`JINA_API_KEY`,
`web_search` uses keyless `html.duckduckgo.com`. Network availability depends on
ABB's egress policy and the upstream service; failures do not have a single
HTTP status. Local runs on 2026-10-23 observed DuckDuckGo HTTP 502 responses.

`web_fetch` also applies Agentao's own SSRF checks before fetching. In those
runs, ABB DNS resolved tested hosts (including `pypi.org`) to synthetic
`198.18.x.x` addresses, which the default guard rejected as non-public. An
allowlisted host is therefore not necessarily reachable through `web_fetch`.
This unit does not relax that guard. Shell tools use a different HTTP client
path: a shell request to the allowed PyPI JSON endpoint succeeded in one run.
Do not infer that every tool or destination is unavailable from a fetch error.

Treat search/fetch errors as environment limitations, not Agent defects by
themselves. The Agent should report failures and distinguish verified fallback
results from information it could not obtain. Requests reaching ABB's egress
observer are recorded there; requests rejected by Agentao before HTTP dispatch
must instead be checked in the tool/runtime evidence.
