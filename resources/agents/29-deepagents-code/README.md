# deepagents-code ACP deployment

This unit installs the pinned [deepagents-code](https://github.com/langchain-ai/deepagents)
CLI release `0.1.72` (PyPI `deepagents-code`, formerly `deepagents-cli`; tag
`deepagents-code==0.1.72`, commit `a764619a`, MIT license) and runs its built-in
ACP server (`deepagents-code --acp`). ABB invokes it over ACP stdio and keeps each
Case in a separate empty workspace. No upstream source is vendored or modified.

The acceptance profile uses Zhipu GLM's OpenAI-compatible coding endpoint.
Supply these variables only at runtime:

- `GLM_API_BASE_URL`: the OpenAI-style base URL, e.g.
  `https://open.bigmodel.cn/api/coding/paas/v4`.
- `GLM_MODEL`: the exact provider model ID, such as `glm-5.1`.
- `GLM_API_KEY`: the Bearer credential. It is never written into this unit.

The interception manifest admits only the tested route:
`POST https://open.bigmodel.cn/api/coding/paas/v4/chat/completions`.
A different OpenAI-compatible provider needs an explicit reviewed route update;
changing environment variables alone does not broaden container egress.

## Installation

`install/requirements.txt` is a fully pinned, `--require-hashes` lock of the
`deepagents-code==0.1.72` closure (including `deepagents==0.7.15` and
`deepagents-acp==0.0.12`) for CPython 3.12, generated from `install/requirements.in`
with `uv pip compile --generate-hashes`. Upstream requires Python >= 3.12, so the
image is based on `python:3.12-bookworm` (the `node:24-bookworm` image ships 3.11).
The agent lives in its own venv `/opt/agent-venv`; ABB's runtime dependencies stay
in `/opt/venv`. Debian's `ripgrep` is installed so the agent's search tool does not
try to download a managed binary.

## Launcher behavior

`bootstrap/launch.py` validates the three variables, then for every Case creates
a disposable `HOME` (and XDG dirs) under `/tmp` and writes
`~/.deepagents/config.toml` there. This keeps deepagents' config, sqlite session
store and state writable by whichever unprivileged uid the runtime chooses and
isolates Cases. It then execs `/opt/agent-venv/bin/deepagents-code --acp`.

- The config sets `[models].default = "openai:$GLM_MODEL"` and an `openai`
  provider with `base_url = $GLM_API_BASE_URL` and `api_key_env = "GLM_API_KEY"`,
  so the credential is read from the environment and never appears in argv or on
  disk. ACP `session/new` does not choose a model, so this default is what runs.
- `[models.providers.openai.params] use_responses_api = false` is required:
  otherwise langchain-openai calls `POST .../v4/responses`, which the GLM coding
  endpoint answers with 404.
- `[update] check = false` and `prices_auto_update = false` (plus the matching
  `DEEPAGENTS_CODE_NO_UPDATE_CHECK`, `_AUTO_UPDATE=0`, `_PRICES_AUTO_UPDATE=0`,
  `_PLUGIN_AUTO_UPDATE=0` variables) stop the PyPI update check and the
  price-list download from raw.githubusercontent.com, which the interceptor would
  otherwise reject as undeclared egress.
- `DEEPAGENTS_CODE_OFFLINE=1` disables managed binary downloads (ripgrep);
  `DEEPAGENTS_CODE_OLLAMA_DISCOVERY=0` disables the local Ollama probe.
- `DEEPAGENTS_CODE_MEMORY_AUTO_SAVE=0` stops the prompt from telling the agent to
  persist "learnings" into `~/.deepagents` memory files outside the workspace.
- An empty `~/.agents/skills` is created; without it startup logs a harmless
  `Cannot load skills ... path_not_found` warning on stderr.
- `DEEPAGENTS_CODE_READ_PROJECT_DOTENV=0` keeps a `.env` in the workspace from
  re-pointing the provider. `LANGSMITH_*`/`LANGCHAIN_*` variables are dropped and
  tracing is forced off, so no runs are sent to LangSmith.

deepagents-code runs in its default (non-Auto, non-YOLO) approval mode, so file
writes, edits and shell commands are sent to ABB as ACP permission requests
(`permission_policy = "allow_once"`); no Auto-mode classifier model is used.
Shell commands run directly in the container (no nested sandbox).

The built-in `fetch_url` tool is always registered by upstream. It contacts the URL
the model chooses; that traffic goes to ABB's egress observer (see "Web tools").
Before #137 such a fetch made the interceptor reject the whole trace.

## Known upstream behavior (non-blocking)

- After a tool permission is granted, `deepagents-acp` 0.0.12 re-sends the text
  the model streamed before that tool call as one extra `agent_message_chunk`,
  so a turn's aggregated ACP output repeats that sentence (seen in the 3-step
  smoke run, where the local Judge flagged it). This is upstream streaming
  behavior on HITL resume; the unit does not patch it.
- The final model call of a Case can be recorded by the interceptor as a native
  `Client disconnected` transport error: the ACP turn ends (`end_turn`) as soon as
  the text is complete and the one-shot worker then closes the agent while the
  HTTP stream is being torn down. The response text is already delivered and host
  trace validation still succeeds.

## Web tools

deepagents-code only adds `web_search` when a Tavily key is present (upstream `main.py`). `TAVILY_API_KEY` is an optional secret (`optional_secret_env_keys`); when it is
supplied, `web_search` are offered and call `api.tavily.com` (`POST /search`),
declared as a tool route in `network/rules.toml`, so requests and results are forwarded
and recorded as tool evidence. Without the key the tools are not offered, as before.
Other non-model traffic goes to ABB's egress observer, which forwards allowlisted hosts
(the package registries by default), refuses the rest with 403 and records every attempt
in `egress.jsonl`; a refusal does not reject the Case (#137).

## Installation inputs

Tracked installation manifests live in install/. Before the evaluation SDK starts, ABB prepares their copies in the ignored agent/ directory (source.method = install). Docker builds use those generated copies. Do not edit agent/; edit install/ instead. If an existing copy differs, move agent/ aside and rerun to regenerate it.
