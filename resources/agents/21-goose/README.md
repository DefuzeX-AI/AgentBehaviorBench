# Goose ACP deployment

This unit installs the pinned [Goose](https://github.com/aaif-goose/goose) release
`1.51.0` (tag `v1.51.0`, commit `1a4249ac`, Apache-2.0) as the upstream prebuilt
Linux binary and runs its built-in ACP server (`goose acp`). ABB invokes it over
ACP stdio and keeps each Case in a separate empty workspace. No upstream source is
vendored or modified.

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

## Distribution

`install/distribution.json` pins
`goose-x86_64-unknown-linux-gnu.tar.bz2` from the `v1.51.0` GitHub release by
sha256 (`de5bf71c…e367e2`). The same digest is listed for that platform in the ACP
registry entry (`agentclientprotocol/registry`, `goose/agent.json`, version
1.51.0). The Dockerfile downloads the archive, checks it with `sha256sum -c`, and
installs the single `goose` binary to `/opt/goose/bin`. The binary needs at most
GLIBC 2.28 / GLIBCXX 3.4.25, which Debian bookworm provides.

## Launcher behavior

`bootstrap/launch.py` validates the three variables (HTTPS base URL without query
or fragment) and prepares, for every Case, a disposable `HOME` under `/tmp` with
the XDG config/data/state/cache directories inside it. This keeps Goose's
sessions database and request logs writable by whichever unprivileged uid the
runtime chooses and isolates Cases.

Goose reads its settings from upper-case environment variables, so no
`config.yaml` is written. The launcher sets:

- a custom OpenAI-engine provider `abb_glm`, written to
  `~/.config/goose/custom_providers/abb_glm.json` in the disposable `HOME`, with
  `base_url = $GLM_API_BASE_URL`, `api_key_env = "GLM_API_KEY"` (the key stays in
  the environment, not the file), a static one-entry model list for `$GLM_MODEL`
  with an explicit context window, and `dynamic_models = false`. With Goose's
  built-in `openai` provider, `goose acp` calls `GET <base>/models` at session
  start (provider inventory refresh) and again for context-window discovery;
  that path is outside the admitted route and the interceptor rejects the trace
  as `egress_denied`. The static custom provider removes both calls. Context
  windows come from upstream's bundled Z.AI definition (`glm-5.1` = 200000);
  unknown models use Goose's default 128000;
- `GOOSE_PROVIDER=abb_glm` and `GOOSE_MODEL=$GLM_MODEL`, so the model is selected
  at startup (ACP `session/new` does not choose one). The OpenAI engine appends
  `/chat/completions` to the base URL, which is exactly the admitted route;
- `GOOSE_TELEMETRY_OFF=1`: upstream otherwise sends usage events to PostHog
  (`us.i.posthog.com`), which would be undeclared egress;
- `GOOSE_DISABLE_SESSION_NAMING=true`: after the first prompt Goose starts a
  background "short title" model call that the one-shot worker would cut when it
  closes ACP. The value must be a boolean literal; `1` is ignored;
- `GOOSE_DISABLE_KEYRING=1`: there is no Secret Service in the container.

### terminal/create adaptation

When the ACP client advertises the terminal capability, Goose's shell tool sends
the whole shell line as `terminal/create` `command` with no `args` (Zed runs that
string through the user's shell). ABB's client executes `command` directly as
argv[0], so every command containing a space failed with `ENOENT`
(`No such file or directory: 'python3 demo.py'`). The launcher therefore runs
Goose as a child process and relays ACP stdio line by line; a `terminal/create`
request without `args` is rewritten to `command = "/bin/sh"`,
`args = ["-c", <original>]`. Execution still happens in ABB's terminal, with the
same permission flow and terminal evidence; all other messages pass through
unchanged. File reads/writes continue to use ACP `fs/*` delegation.

## Known behavior

- Goose's system prompt advertises capabilities such as web research and
  extensions; none are provisioned here, and requests beyond the model route are
  blocked.
- Goose keeps per-Case request logs under `~/.local/state/goose/logs` in the
  disposable `HOME`; they contain prompts but not the credential and are discarded
  with the container.

## Installation inputs

Tracked installation manifests live in install/. Before the evaluation SDK starts, ABB prepares their copies in the ignored agent/ directory (source.method = install). Docker builds use those generated copies. Do not edit agent/; edit install/ instead. If an existing copy differs, move agent/ aside and rerun to regenerate it.
