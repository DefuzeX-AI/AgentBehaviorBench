# OpenHands CLI ACP deployment

This unit installs the pinned [OpenHands CLI](https://github.com/OpenHands/OpenHands-CLI)
release `1.16.0` (PyPI `openhands`, tag `1.16.0`, commit `2963442d`, MIT) and runs its
built-in ACP server (`openhands acp`). It pulls OpenHands SDK/tools `1.21.0`. ABB invokes
it over ACP stdio and keeps each Case in a separate empty workspace. No upstream source is
vendored or modified.

This unit uses default model selection; no `[model]` declaration is needed. Configure the selected provider in
`.env`: OpenRouter -> DeepSeek -> GLM, choosing the first nonempty API key, or set
`ABB_MODEL_PROVIDER` explicitly. Supply the selected provider's model name as well.
See [model selection](../../../docs/Model-Selection.md) for variables and constraints.

ABB passes the resolved configuration through internal `ABB_AGENT_MODEL_API_KEY`,
`ABB_AGENT_MODEL_BASE_URL`, `ABB_AGENT_MODEL` and `ABB_AGENT_MODEL_PROVIDER` variables.
Users do not fill these internal variables. Only the selected credential reaches the
launcher. The runtime derives the exact observed model route from the selected URL.

The runtime admits the exact `POST <selected-base>/chat/completions` route.

## What is pinned

- `install/requirements.txt` is a fully resolved, hash-locked lock of `openhands==1.16.0`
  for CPython 3.12 on x86_64 Linux, generated with
  `uv pip compile --generate-hashes` (the command is recorded in the file header).
  The image installs it with `pip --require-hashes --no-deps` into its own venv
  `/opt/openhands`, separate from the ABB runtime venv `/opt/venv`.
- The base image is `python:3.12-bookworm` because the CLI requires Python `==3.12.*`.
  `tmux` is installed because the terminal tool prefers a `tmux -L openhands` session.
- OpenHands' public skills repository, [OpenHands/extensions](https://github.com/OpenHands/extensions),
  is fetched once at image build time at commit `f761809704f3edb2f25e737991277e1bb1ac3e88`
  (Dockerfile `ARG EXTENSIONS_COMMIT`) into the local bare mirror `/opt/openhands-extensions.git`.

## Launcher behavior

For every Case `bootstrap/launch.py` validates the three variables, creates a disposable
`HOME` under `/tmp` (plus `XDG_*` directories inside it), and then:

1. **Writes `~/.openhands/agent_settings.json` before starting ACP (upstream limitation).**
   In ACP mode OpenHands 1.16.0 answers `session/new` with "Authentication required" unless
   that file exists, and `openhands acp --override-with-envs` is ignored. The launcher runs
   the CLI's own `AgentStore().save(AgentStore().load_or_create(env_overrides_enabled=True))`
   with `LLM_API_KEY`, `LLM_BASE_URL` and `LLM_MODEL=openai/$ABB_AGENT_MODEL` in that one child's
   environment. The resulting file holds the credential, so it lives only in the disposable
   `HOME` with mode `0600`; the key is never on argv. `ABB_AGENT_MODEL_API_KEY`/`LLM_API_KEY` are then
   removed from the ACP server's environment, so the agent's terminal cannot echo it.
2. **Removes startup egress.** Any undeclared request makes the host reject the trace:
   - `LITELLM_LOCAL_MODEL_COST_MAP=True` stops LiteLLM from downloading its cost map from
     `raw.githubusercontent.com`.
   - `load_public_skills=True` is hardcoded in the CLI, and every session clones or
     `git fetch`es `https://github.com/OpenHands/extensions`. There is no switch to turn it
     off, so the launcher writes `$HOME/.gitconfig` in the disposable HOME mapping that URL to
     the baked mirror with git's `url.<mirror>.insteadOf`, plus `safe.directory` for the
     root-owned mirror (git ignores `safe.directory` set through `GIT_CONFIG_*` variables and
     otherwise refuses the clone with "dubious ownership" when the runtime uid differs).
     Skills therefore load from the pinned commit with no network.
   - `OPENHANDS_SUPPRESS_BANNER=1`; the PyPI update check only runs in the TUI splash,
     not in ACP mode.
3. Execs `/opt/openhands/bin/openhands acp` **without** `--always-approve`. The default
   `always-ask` confirmation mode sends each pending action to ABB as
   `session/request_permission`; ABB's `permission_policy = "allow_once"` picks the first
   `allow_once` option (`accept`, "Yes, proceed").

## Known non-blocking behavior

- The CLI's default agent includes an `LLMSummarizingCondenser` that only runs after 80
  events; short Cases never reach it. There is no background title generation in ACP mode.
- The default agent spec requests `reasoning_effort: high`; LiteLLM drops parameters the
  endpoint does not accept (`drop_params: true`).

## Installation inputs

Tracked installation manifests live in install/. Before the evaluation SDK starts, ABB prepares their copies in the ignored agent/ directory (source.method = install). Docker builds use those generated copies. Do not edit agent/; edit install/ instead. If an existing copy differs, move agent/ aside and rerun to regenerate it.

## Validation scope

Earlier acceptance records describe the previous fixed-provider deployment. They do not
certify every shared provider/model combination; run a fresh Case after changing it.
