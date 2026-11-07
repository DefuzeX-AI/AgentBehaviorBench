# Zeph ACP deployment

This unit installs the pinned [Zeph](https://github.com/bug-ops/zeph) release `0.22.5`
(tag `v0.22.5`, commit `6673e1f0`, MIT) as the upstream prebuilt static Linux binary (built
with the ACP feature) and runs its ACP server (`zeph --acp`). ABB invokes it over ACP stdio
and keeps each Case in a separate empty workspace. No upstream source is vendored or
modified.

This unit uses default model selection; no `[model]` declaration is needed. ABB passes
the resolved configuration through `ABB_AGENT_MODEL_API_KEY`, `ABB_AGENT_MODEL_BASE_URL`
and `ABB_AGENT_MODEL`; the runtime admits the exact `POST <selected-base>/chat/completions`
route.

**Depends on #555**: Zeph runs commands and writes files through ABB's ACP terminal and
`fs/*` methods.

## Distribution

`install/distribution.json` pins `zeph-x86_64-unknown-linux-musl.tar.gz` from the `v0.22.5`
GitHub release by sha256 (`5d6061a7…6328e8a5f2`, the release's `.sha256` file), and the
`config/default.toml` of the same commit by sha256 (`26aaafaa…4d26276`). The Dockerfile
downloads and checks both, installs `zeph` to `/opt/zeph/bin` and the config template to
`/opt/zeph/share/default.toml`.

## Launcher behavior

`bootstrap/launch.py` validates the model variables (HTTPS base URL without query or
fragment), creates a disposable `HOME` per Case and runs
`zeph --config ~/.config/zeph/config.toml --acp` as a child process.

**Config.** Zeph refuses a config that leaves out any section, so the launcher starts from
the pinned `default.toml` and changes two things: its single local-Ollama provider becomes
one `compatible` (OpenAI Chat Completions) provider named `abb` with the selected model, and
the vault backend becomes `env`. Zeph then reads the key from `ZEPH_COMPATIBLE_ABB_API_KEY`
in the environment; it is never written to disk or put on the command line.

**Model relay (`bootstrap/model_relay.py`).** In the first smoke Zeph opened connections to
the model host that were not the admitted route before its first chat call, and the runtime
then sent the chat call itself through the egress observer, which refused it
(`refused HTTP CONNECT request: 403`). The provider's `base_url` is therefore a plain-HTTP
relay on an ephemeral `127.0.0.1` port (added to `NO_PROXY`). The relay sends each
`POST /chat/completions` on a fresh HTTPS connection to the selected base URL through the
runtime's `HTTPS_PROXY` with Python's default TLS context, and streams the response back
unchanged; anything else gets a local 404. Every model call is still intercepted and recorded.

**ACP stdio relay.** The launcher relays ACP stdio and adapts three things to ABB's client:

- *terminal/create*: Zeph's bash tool lets the model fill `command` and `args`, and the model
  often puts a whole command line in `command` (with no args, with its arguments repeated in
  `args`, or with `args = ["-c"]`). ABB runs `command` as argv[0], so these failed with ENOENT.
  A `command` containing whitespace is run as `/bin/sh -c <command>`.
- *Missing-file reads*: before `write_file` Zeph reads the old content for a diff and treats
  ACP `ResourceNotFound` (-32002) as a new file (`zeph-acp` `fs.rs` `ReadForDiff`). ABB answers
  a read of a missing file with `Internal error` carrying `[Errno 2] No such file or
  directory`, so every new-file write failed; the relay rewrites that error to -32002.
- *Workspace cleanup*: Zeph keeps per-project state in `<workspace>/.zeph` (sessions) and
  creates it 0755, which the host cannot clean up (`PermissionError … .zeph/sessions`). Before
  each `session/prompt` reply is passed on, and again on exit, the launcher makes the
  directories it owns under the workspace `0777`. It also sets `umask 0`.

Zeph's default permission behavior is kept; commands and writes are requested through
`session/request_permission` and answered by ABB's `allow_once` policy.
