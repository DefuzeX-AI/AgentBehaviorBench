# VT Code ACP deployment

This unit installs the pinned [VT Code](https://github.com/vinhnx/VTCode) release
`0.180.5` as its official prebuilt Linux binary and runs its built-in ACP server
(`vtcode acp standard`, `src/cli/acp.rs`). ABB invokes it over ACP stdio and keeps
each Case in a separate empty workspace. No upstream source is vendored or modified.

The recorded source revision `ea28d485` is the commit of tag `0.180.5`, from which
upstream CI built the release binaries. `agent add` imported the default branch on
2026-10-24 at `19be02c4`, 19 commits past the tag; the snapshot and the recorded
revision were reset to the tag so that they describe the deployed binary.

## Licence

Apache-2.0 (`LICENSE` in the repository, which GitHub reports as Apache-2.0; the
crate metadata in `Cargo.toml` declares `MIT OR Apache-2.0`). The unit only
downloads the unmodified release archive at build time.

## Model provider

This unit uses default model selection; no `[model]` declaration is needed. Configure the selected provider in
`.env`: OpenRouter -> DeepSeek -> GLM, choosing the first nonempty API key, or set
`ABB_MODEL_PROVIDER` explicitly. Supply the selected provider's model name as well.
See [model selection](../../../docs/Model-Selection.md) for variables and constraints.

ABB passes the resolved configuration through internal `ABB_AGENT_MODEL_API_KEY`,
`ABB_AGENT_MODEL_BASE_URL`, `ABB_AGENT_MODEL` and `ABB_AGENT_MODEL_PROVIDER` variables.
Users do not fill these internal variables. Only the selected credential reaches the
launcher. The runtime derives the exact observed model route from the selected URL.

VT Code's OpenAI-compatible custom provider with `api_format = "openai-chat"` posts
to `<base_url>/chat/completions`, which is the exact route the runtime admits.

## Installation

`install/distribution.json` pins, for `aarch64` and `x86_64`, the release archive
`vtcode-0.180.5-<arch>-unknown-linux-gnu.tar.gz` and its SHA-256 as published in the
release's `checksums.txt`. The Dockerfile selects the entry for `uname -m`, verifies
the download with `sha256sum -c`, extracts only `./vtcode` to `/opt/vtcode/bin` and
runs `vtcode --version`. The binary needs only glibc, libstdc++ and libgcc and uses
rustls with the system roots, so the image is `python:3.12-slim-bookworm` plus
`ca-certificates`. A source build of the Rust workspace is not used: it would need a
full Rust toolchain and far more memory than the binary download, and would not
change the deployed program.

`ripgrep` and `git` are installed from Debian for the agent's shell commands.

## Launcher behavior

`bootstrap/launch.py` validates the three variables (HTTPS base URL without query
or fragment), creates a disposable directory under `/tmp` for every Case and points
`XDG_CONFIG_HOME`, `XDG_DATA_HOME`, `XDG_STATE_HOME`, `XDG_CACHE_HOME`,
`XDG_BIN_HOME` and `VTCODE_HOME` into it, so VT Code's config, sessions, trust
records and caches stay out of the Case workspace and are writable by whichever
unprivileged uid the runtime chooses. It then `exec`s `/opt/vtcode/bin/vtcode acp
standard`, which owns the ACP stdio channel directly. It writes:

- `vtcode.toml`, selected through `VTCODE_CONFIG_PATH` (the explicit-file layer,
  which replaces the workspace `vtcode.toml` layer, so a Case cannot redirect the
  provider by writing one). It defines one custom provider `abb`
  (`base_url` = `ABB_AGENT_MODEL_BASE_URL`, `model` = `ABB_AGENT_MODEL`,
  `api_format = "openai-chat"`) selected as `[agent] provider`, with
  `api_key_env = "ABB_AGENT_MODEL_API_KEY"`, so VT Code reads the key from the
  environment and it never appears in argv or on disk. It enables `[acp]` and
  `[acp.zed]` (stdio) and disables persistent memories, checkpoints and the local
  ATIF/dashboard/perf diagnostics, and sets the internal `apply_patch` policy to
  `allow` (see below);
- `update.toml` with `check_interval_hours = 0`, which disables release checks
  against the GitHub API.

The launcher removes native provider keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`,
`GEMINI_API_KEY`, `OPENROUTER_API_KEY` and others) from the child environment so the
built-in providers stay unused.

## Tools and permissions

Over ACP the model sees `read_file`, `list_files`, `apply_patch`, `exec_command` and
`write_stdin`; the session's primary agent is `build`. `read_file` goes through the
client's `fs/read_text_file`. `apply_patch` and `exec_command` send ACP
`session/request_permission`, which ABB answers with its `allow_once` policy.
Non-PTY commands run directly in the container through VT Code's pipe runner; PTY
requests are routed to ACP client terminals.

The launcher sets `[tools.policies] apply_patch = "allow"`. In this release the
ACP bridge first asks the client for permission and then re-checks VT Code's
internal tool policy, whose default for `apply_patch` is `prompt`. Under ACP that
second prompt has no handler and denies every edit (`[Blocked by policy] tool denied
by policy`), even after the client allowed it; the first acceptance run hit this
and fell back to a shell heredoc. With `allow` the ACP permission request remains
the only gate: an offline check with a `reject_once` answer still cancels the patch
("permission denied by the user"). `exec_command` and `write_stdin` already default
to `allow` internally and are gated the same way.

## Known non-blocking noise

VT Code keeps native per-workspace state under `<workspace>/.vtcode/`
(`tool-policy.json` and spooled tool outputs under `context/tool_outputs/`). When
workspace file evidence is collected, these files can appear in it; they are
upstream behaviour, not changes the task asked for.

## Installation inputs

Tracked installation manifests live in install/. Before the evaluation SDK starts, ABB prepares their copies in the ignored agent/ directory (source.method = install). Docker builds use those generated copies. Do not edit agent/; edit install/ instead. If an existing copy differs, move agent/ aside and rerun to regenerate it.

## Validation scope

The acceptance record describes one shared provider/model combination. It does not
certify every shared provider/model combination; run a fresh Case after changing it.
