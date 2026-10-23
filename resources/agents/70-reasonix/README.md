# Reasonix ACP deployment

This unit installs the pinned [Reasonix](https://github.com/esengine/DeepSeek-Reasonix)
release `2.49.0` (tag `v2.49.0`, commit `2ddc6f64`, MIT) as the upstream prebuilt
Linux binary and runs its built-in ACP server (`reasonix acp`). ABB invokes it over
ACP stdio and keeps each Case in a separate empty workspace. No upstream source is
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

## Distribution

`install/distribution.json` pins `reasonix-linux-amd64.tar.gz` from the `v2.49.0`
GitHub release by sha256 (`416dbdaf…3bd14`). The Dockerfile downloads the archive,
checks it with `sha256sum -c`, and installs the single `reasonix` binary to
`/opt/reasonix/bin`. The archive also carries a web frontend directory that the ACP
server does not use; only the binary member is extracted. The binary is statically
linked (`CGO_ENABLED=0`), so it needs no runtime beyond glibc.

Release `studio-v2.49.0` publishes the same CLI archive; the two tags resolve to the
same commit for everything this unit exercises.

## Launcher behavior

`bootstrap/launch.py` validates the three variables (HTTPS base URL without query or
fragment) and prepares, for every Case, a disposable `REASONIX_HOME` under `/tmp`.

Reasonix resolves configuration and credentials from its home directory alone:

- `config.toml` declares one static OpenAI-compatible provider `abb` with
  `base_url = $ABB_AGENT_MODEL_BASE_URL` and a **one-entry static `models` list** for
  `$ABB_AGENT_MODEL`. Upstream can discover models over `GET <base>/models`; that
  path is outside the admitted route, so the static list removes the call. The
  provider's default model is written as `abb/$ABB_AGENT_MODEL`, which is also the
  global `default_model`.
- `.env` names the credential. Reasonix reads provider keys from
  `<Reasonix home>/.env` and **never** from the process environment, so a container
  environment variable alone would not configure anything; the launcher writes the
  file and passes the key to the child only as the variable that file names. The file
  is mode `0600` and is not in `config.toml`.

`reasonix acp` is started with:

- `--profile balanced` — the runtime-profile flag. Upstream `docs/ACP.md` documents a
  `--preset` spelling that belongs to `run`/`tui`; the `acp` flagset rejects it.
- `--permission-mode auto` — sessions otherwise open in `ask`, which would leave
  every approval card to the client. `auto` approves ordinary tool use while keeping
  deny rules and plan confirmation in force.
- `--sandbox-bash auto` — upstream's Linux default is `enforce`, and bubblewrap
  cannot create its namespaces inside a default container, so `enforce` refuses every
  shell command. This unit leaves the sandbox in the release's container posture; the
  container is the boundary. See the upstream note on dev containers and
  `[sandbox] bash = "off"`.
- `--workspace-only` — confines writes to the session workspace.

## stdout contract

`reasonix acp` writes JSON-RPC to stdout and all diagnostics to stderr, so the
launcher passes stdio through unchanged and needs no relay.
