# code-assistant ACP deployment

This unit installs the pinned [code-assistant](https://github.com/stippi/code-assistant)
release `0.2.16` (tag `v0.2.16`, commit `b942737b`, MIT) as the upstream prebuilt Linux
binary and runs its ACP mode (`code-assistant acp`). ABB invokes it over ACP stdio and keeps
each Case in a separate empty workspace. No upstream source is vendored or modified.

This unit uses default model selection; no `[model]` declaration is needed. ABB passes
the resolved configuration through `ABB_AGENT_MODEL_API_KEY`, `ABB_AGENT_MODEL_BASE_URL`
and `ABB_AGENT_MODEL`; the runtime admits the exact `POST <selected-base>/chat/completions`
route.

**Depends on #555** (see "Terminal commands" below).

## Distribution

`install/distribution.json` pins `code-assistant-linux-x86_64.zip` from the `v0.2.16`
GitHub release by sha256 (`492dfea8…5340e0a8ce0`; the release publishes no checksum file,
so the value was computed from the downloaded asset). The Dockerfile downloads it, checks it
with `sha256sum -c`, extracts the single `code-assistant` binary to
`/opt/code-assistant/bin` and runs `--version`. The binary is the same as the GUI build: it
needs glibc 2.39 or newer and links libxkbcommon/libxkbcommon-x11/libxcb even when no window
is opened, so the image is based on `python:3.12-slim-trixie` with those libraries installed.

## Launcher behavior

`bootstrap/launch.py` validates the model variables (HTTPS base URL without query or
fragment), creates a disposable `HOME` per Case and writes two files to
`~/.config/code-assistant/` (the v0.2.16 release reads `models.json`, not the newer
`model-selection.json` that the current docs describe):

- `providers.json`: one provider `abb` of type `openai` (Chat Completions) with
  `base_url = <selected base>` and `api_key = "${ABB_AGENT_MODEL_API_KEY}"`, which
  code-assistant expands at load time, so the key is never written to disk. The client sends
  `POST <base_url>/chat/completions`.
- `models.json`: one model named after the selected model id, pointing at `abb`, with an
  explicit 128k `context_token_limit` because the id is not in code-assistant's catalog.

It then runs `code-assistant --config-dir <dir> acp --model <model>`. code-assistant's
default command sandbox mode (`danger-full-access`) is kept.

**Terminal commands.** code-assistant's `execute_command` sends the whole command line as
`terminal/create` `command` with no `args`, as Goose does (see `17-goose`). ABB's client runs
`command` directly as argv[0], so every command containing a space failed with ENOENT and
code-assistant fell back to its own PTY after several failed attempts. The launcher runs
code-assistant as a child and relays ACP stdio; a `terminal/create` with a string command
and no args is rewritten to `command = "/bin/sh"`, `args = ["-c", <original>]`, so commands
keep running in ABB's terminal with the same evidence. Commands therefore create files in the
host-owned workspace through ABB's terminal; without #555 a `__pycache__` directory created
by `python3 -m unittest` is left 0755 and owned by the container uid, host cleanup fails with
`PermissionError` and the Case is reported BLOCKED. The launcher also sets `umask 0` for
code-assistant's own processes.
