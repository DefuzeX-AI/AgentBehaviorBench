# jcode ACP deployment

This unit installs the pinned [jcode](https://github.com/1jehuang/jcode) release
`0.87.1` (tag `v0.87.1`, commit `944f747e`, MIT) as the upstream prebuilt Linux
binary and runs its built-in ACP adapter (`jcode acp`, "Run as an Agent Client
Protocol (ACP) adapter backed by the Jcode daemon"). ABB invokes it over ACP stdio
and keeps each Case in a separate empty workspace. No upstream source is vendored
or modified.

The acceptance profile uses Zhipu GLM's OpenAI-compatible coding endpoint.
Supply these variables only at runtime:

- `GLM_API_BASE_URL`: the OpenAI-style base URL, e.g.
  `https://open.bigmodel.cn/api/coding/paas/v4`.
- `GLM_MODEL`: the exact provider model ID, such as `glm-5.1`.
- `GLM_API_KEY`: the Bearer credential. It is never written into this unit or
  into jcode's config file.

The interception manifest admits only the tested model route:
`POST https://open.bigmodel.cn/api/coding/paas/v4/chat/completions`.
A different OpenAI-compatible provider needs an explicit reviewed route update;
changing environment variables alone does not broaden container egress.

## Distribution

`install/distribution.json` pins `jcode-linux-x86_64.tar.gz` from the `v0.87.1`
GitHub release by sha256 (`6a6cf23d…d2808371`, the value in the release's
`SHA256SUMS`). The archive holds a small POSIX-sh wrapper
(`jcode-linux-x86_64`, which sets `LD_LIBRARY_PATH` and execs the binary) and
the ELF binary `jcode-linux-x86_64.bin`. The Dockerfile downloads the archive,
checks it with `sha256sum -c`, installs both files to `/opt/jcode/bin` and links
`jcode` to the wrapper. The binary needs at most GLIBC 2.17.

## Daemon lifecycle and Case isolation

`jcode acp` is a thin ACP front end. On the first `session/new` it spawns the
jcode daemon (`jcode serve`, detached with `setsid`, so it leaves the ACP
process group) and talks to it over a Unix socket; the daemon runs the model
loop and all tools. `bootstrap/launch.py` therefore:

- creates a disposable `HOME` under `/tmp` for every launch, with
  `JCODE_HOME=$HOME/.jcode` (config, sessions, sqlite databases, logs, caches)
  and `JCODE_RUNTIME_DIR`/`XDG_RUNTIME_DIR=$HOME/run` (mode 0700; daemon
  socket and spawn lock). A daemon can only ever be found and reused by the
  same launch, so Cases never share a daemon, session or history, and every
  path is writable by whichever unprivileged uid the runtime selects;
- runs `jcode acp` as a child with inherited stdio (jcode speaks spec ACP; no
  message rewriting is needed);
- after the ACP process exits (or on SIGTERM/SIGINT/SIGHUP, which are
  forwarded), runs `jcode server stop --json` with the same environment, which
  SIGTERMs the daemon's process group and escalates to SIGKILL, and then kills
  any remaining process whose environment still carries this launch's
  `JCODE_HOME`. Verified on the host: no `jcode serve` process survives a
  session.

## Configuration

The launcher writes `$JCODE_HOME/config.toml` (no secret in it):

- a named profile `[providers.abb-glm]` with `type = "openai-compatible"`,
  `base_url = $GLM_API_BASE_URL`, `api_key_env = "GLM_API_KEY"`,
  `default_model = $GLM_MODEL` and one static `[[providers.abb-glm.models]]`
  entry with an explicit context window (200000 for `glm-5.1`; unknown models
  use 128000). `model_catalog` stays off, so jcode never calls
  `GET <base>/models`. It is selected with `[provider] default_provider`;
  cross-provider failover is set to `manual`;
- `[acp] tool_profile = "acp"` (upstream's default for `jcode acp`: core coding
  tools plus `batch`), `profile = "standard"` (spec-only ACP messages);
- `[features] check_updates = false`, `memory = false`, `swarm = false`;
  `[ambient] enabled = false`; `[sponsors] enabled = false` (integration
  discovery would call `api.jcode.sh`).

Environment set for the child: `JCODE_NO_TELEMETRY=1` and `DO_NOT_TRACK=1`
(usage telemetry), `JCODE_DISABLE_PRICING_REFRESH=1` (the daemon otherwise
downloads the models.dev pricing catalog at start), `JCODE_NO_AUTO_UPDATE=1`,
`JCODE_NO_BROWSER=1`, `JCODE_NO_MENUBAR=1`, `JCODE_DISABLE_POWER_INHIBIT=1`, and
`TOKIO_WORKER_THREADS=4` so the two Rust runtimes (ACP front end + daemon) stay
well inside the container's pids limit instead of starting one worker per host
CPU.

## Network routes

Besides the model route, `network/rules.toml` declares one optional
loopback-only metadata route: `GET http://localhost:{11434,1234}/v1/models`.
While a named OpenAI-compatible profile is active, jcode's background catalog
sweep (about 10 s after the daemon starts, then every 60 s) treats the keyless
built-in Ollama and LM Studio profiles as configured and asks them for a model
list. Without the route the interceptor rejected the trace as `egress_denied
localhost /v1/models`. Nothing listens on those ports, so the request fails
locally (ABB records it as a non-required `tool_error`) and no traffic leaves
the container. There is no upstream setting that turns that sweep off.

## Evidence

jcode executes its tools inside its daemon rather than through ACP `fs/*` or
`terminal/*` delegation. ACP evidence therefore consists of `tool_call` /
`tool_call_update` notifications (kind and title, e.g. `edit` / "Writing file",
`execute` / "Running shell command"), streamed `agent_message_chunk` text,
`usage_update` and the prompt result usage. File effects are captured by ABB's
workspace file evidence (`track_files`), and model requests/responses by the
interceptor.

## Known behavior

- jcode's system prompt describes capabilities (web search, browser, email,
  swarm, memory) that are not provisioned here; the `acp` tool profile and the
  disabled features keep those tools off, and requests beyond the model route
  are blocked.
- The daemon keeps per-Case logs and session JSON under `$JCODE_HOME` in the
  disposable `HOME`; they contain prompts but not the credential and are
  discarded with the container.

## Installation inputs

Tracked installation manifests live in install/. Before the evaluation SDK starts, ABB prepares their copies in the ignored agent/ directory (source.method = install). Docker builds use those generated copies. Do not edit agent/; edit install/ instead. If an existing copy differs, move agent/ aside and rerun to regenerate it.
