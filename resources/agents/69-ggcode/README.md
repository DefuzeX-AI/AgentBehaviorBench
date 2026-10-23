# ggcode ACP deployment

This unit installs the pinned [ggcode](https://github.com/topcheer/ggcode) release `1.3.266`
(tag `v1.3.266`, commit `6b51d84e`, MIT) as the upstream prebuilt Linux binary and runs its
built-in ACP server (`ggcode acp`). ABB invokes it over ACP stdio and keeps each Case in a
separate empty workspace. No upstream source is vendored or modified.

This unit uses default model selection; no `[model]` declaration is needed. ABB passes
the resolved configuration through `ABB_AGENT_MODEL_API_KEY`, `ABB_AGENT_MODEL_BASE_URL`
and `ABB_AGENT_MODEL`; the runtime admits the exact `POST <selected-base>/chat/completions`
route.

## Distribution

`install/distribution.json` pins `ggcode_linux_x86_64.tar.gz` from the `v1.3.266` GitHub
release by sha256 (`06ccfe2a…4dfad4f`, the release's
`checksums.txt` entry). The Dockerfile downloads it, checks it with `sha256sum -c` and
installs the single `ggcode` binary to `/opt/ggcode/bin`.

## Launcher behavior

`bootstrap/launch.py` validates the model variables (HTTPS base URL without query or
fragment), creates a disposable `HOME` per Case, writes `~/.ggcode/ggcode.yaml` with one
vendor `abb` whose single OpenAI-protocol endpoint is the selected base URL and model, and
runs `ggcode --config <that file> acp`. The endpoint's `api_key` is the literal
`${ABB_AGENT_MODEL_API_KEY}`, which ggcode expands when it loads the file, so the key is
never written to disk or put on the command line. ggcode's default ACP permission mode
(`supervised`) is kept; requests it raises are answered by ABB's `allow_once` policy.

The launcher runs ggcode as a child and relays ACP stdio, adapting two things:

- **End of turn.** ggcode answers `session/prompt` at once with `{"stopReason": ""}` and
  reports the end of the turn later with a non-standard `session/prompt_complete`
  notification (`internal/acp/handler.go`, `handleSessionPrompt`). An ACP client treats
  the first reply as the end of the turn, so the relay holds it and answers the request
  with the stop reason from the matching `prompt_complete` (empty becomes `end_turn`).
  Error replies pass through unchanged.
- **Workspace cleanup.** ggcode keeps project state in `<workspace>/.ggcode/` (memory,
  trajectory learnings, perf baseline) and creates those directories with an explicit
  `0755`, which `umask 0` cannot widen. ABB removes the Case workspace from the host after
  the run, and the host cannot delete entries in a `0755` directory owned by the container
  uid (the first smoke was BLOCKED by `PermissionError … .ggcode/memory`). Before each turn
  is reported complete, and again on exit, the launcher makes the directories it owns under
  the workspace `0777`. The launcher also sets `umask 0` for everything else.

ggcode runs its tools (file writes and shell commands included) itself inside the
container; the smoke made no ACP `fs/*` or `terminal/*` requests and no permission requests.

Known noise: one connection to `gateway.ggcode.dev:443` (ggcode's remote relay,
`internal/tunnel/session.go` `DefaultRelayURL`) is refused by the egress policy; the turn is
unaffected.
