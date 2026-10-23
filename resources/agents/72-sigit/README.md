# siGit Code ACP deployment

This unit installs the pinned [siGit Code](https://github.com/getsigit/sigit)
release `1.7.4` (tag `v1.7.4`, commit `e0ec5cf3`, Apache-2.0) as the upstream
prebuilt Linux binary and runs its built-in ACP server (`sigit --acp`). ABB
invokes it over ACP stdio and keeps each Case in a separate empty workspace. No
upstream source is vendored or modified.

This unit uses default model selection; no `[model]` declaration is needed.
Configure the selected provider in `.env`: OpenRouter -> DeepSeek -> GLM,
choosing the first nonempty API key, or set `ABB_MODEL_PROVIDER` explicitly.
Supply the selected provider's model name as well. See
[model selection](../../../docs/Model-Selection.md) for variables and constraints.

ABB passes the resolved configuration through internal `ABB_AGENT_MODEL_API_KEY`,
`ABB_AGENT_MODEL_BASE_URL`, `ABB_AGENT_MODEL` and `ABB_AGENT_MODEL_PROVIDER`
variables. Users do not fill these internal variables. Only the selected
credential reaches the launcher. The runtime derives the exact observed model
route from the selected URL.

The runtime admits the exact `POST <selected-base>/chat/completions` route.

## Distribution

`install/distribution.json` pins the `sigit-linux-amd64` binary from the `v1.7.4`
GitHub release by sha256 (`eace6933…f758197`). The Dockerfile downloads the
binary, checks it with `sha256sum -c`, and installs it to `/opt/sigit/bin`. The
binary needs at most GLIBC 2.39, which Debian trixie provides.

## Launcher behavior

`bootstrap/launch.py` validates the three variables (HTTPS base URL without query
or fragment) and prepares, for every Case, a disposable `HOME` under `/tmp` with
`~/.config/sigit` inside it. This keeps siGit Code's providers file, sessions and
logs writable by whichever unprivileged uid the runtime chooses and isolates Cases.

siGit Code reads its provider override from environment variables, so no config
file is written. The launcher sets:

- `OPENAI_BASE_URL=$ABB_AGENT_MODEL_BASE_URL`, `OPENAI_API_KEY=$ABB_AGENT_MODEL_API_KEY`
  (the key stays in the environment, never on disk) and `SIGIT_MODEL=$ABB_AGENT_MODEL`.
  siGit Code's explicit provider override (`OPENAI_BASE_URL` + `OPENAI_API_KEY`)
  wins over its on-device and cloud paths, so no local model is loaded and no
  sign-in is required. Its OpenAI backend appends `/chat/completions` to the base
  URL, which is exactly the admitted route;
- `SIGIT_MCP_OFFICIAL=off`: the official siGit MCP server needs a signed-in session
  and would otherwise be advertised to the model as a reachable tool, producing
  undeclared egress;
- `ONDE_DISABLE_PULSE=1`: on-device telemetry is compiled out of release builds,
  but this keeps it off if the image ever runs a build with it enabled.

The launcher then `exec`s `sigit --acp`, so the ACP JSON-RPC stream on stdout and
the logs on stderr pass straight through to ABB. siGit Code sends foreground
`run_command` calls through the client terminal and file reads/writes through the
client filesystem when the client advertises them, which ABB's client does; both
fall back to the local disk and shell inside the container.

## Known behavior

- siGit Code's system prompt describes a general coding agent with local tools.
  None of its cloud, browser or MCP surfaces are provisioned here, and requests
  beyond the model route are blocked.
- The first launch of an on-device model would normally download a GGUF from
  Hugging Face; the explicit provider override avoids that path entirely, so no
  model download or local inference happens in this deployment.

## Installation inputs

Tracked installation manifests live in `install/`. Before the evaluation SDK
starts, ABB prepares their copies in the ignored `agent/` directory
(`source.method = install`). Docker builds use those generated copies. Do not
edit `agent/`; edit `install/` instead. If an existing copy differs, move
`agent/` aside and rerun to regenerate it.

## Validation scope

This unit has not yet been certified against a live shared provider/model
combination. Run a fresh Case after configuring `.env` to confirm native
requests and tool behavior.
