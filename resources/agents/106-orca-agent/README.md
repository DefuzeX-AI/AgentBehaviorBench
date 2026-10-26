# Orca ACP deployment

This unit installs the pinned [Orca](https://github.com/echoVic/orca-agent) release `0.5.13`
(tag `v0.5.13`, commit `bbe6ef39`, MIT) as the upstream prebuilt Linux binary and runs its
built-in ACP mode (`orca --mode=acp`). ABB invokes it over ACP stdio and keeps each Case in
a separate empty workspace. No upstream source is vendored or modified.

This unit uses default model selection; no `[model]` declaration is needed. ABB passes
the resolved configuration through `ABB_AGENT_MODEL_API_KEY`, `ABB_AGENT_MODEL_BASE_URL`
and `ABB_AGENT_MODEL`; the runtime admits the exact `POST <selected-base>/chat/completions`
route.

## Distribution

`install/distribution.json` pins `orca-x86_64-unknown-linux-gnu.tar.gz` from the `v0.5.13`
GitHub release by sha256 (`00c1dbb0…dbb2fc4418bf`, the value in the release's `.sha256`
file). The Dockerfile downloads it, checks it with `sha256sum -c` and installs the single
`orca` binary to `/opt/orca/bin`. The binary requires glibc 2.39 or newer, so the image is
based on `python:3.12-slim-trixie` rather than bookworm (glibc 2.36).

## Launcher behavior

`bootstrap/launch.py` validates the model variables (HTTPS base URL without query or
fragment), creates a disposable `HOME` per Case and runs as a child, relaying ACP stdio:

```
orca --mode=acp --model <model>
```

with `DEEPSEEK_BASE_URL=<base>` and `ORCA_API_KEY=<key>`, the environment variables Orca
documents for the endpoint and key. Its DeepSeek provider sends
`POST <base>/chat/completions`. The key is never on the command line or on disk.

**Execution policy (`ORCA_MODE=full-auto`).** In its default modes Orca runs shell
commands only under an OS sandbox (bubblewrap on Linux); when no backend can enforce the
policy it removes the shell tool for the session ("fail closed"). The runtime container
does not let bubblewrap create its namespaces, so the first smoke could write files but
could not run its tests. The launcher sets `ORCA_MODE=full-auto`, which Orca documents as
the explicit trusted-host policy (`docs/architecture/capability-kernel.md`: "restoring
shell execution requires repairing the backend or an explicit user-selected trusted-host
policy. `full-auto` selects that policy"). Commands then run directly in the Case
container, which is the isolation boundary, and Orca does not ask for approval.

**Pricing refresh.** At startup Orca refreshes DeepSeek prices from `models.dev`, which
the egress policy refuses. The launcher writes `~/.orca/config.toml` with
`[pricing] refresh = false`, the switch Orca's README documents.

**User questions (`ask_user_question`).** Orca always offers this tool over ACP and asks
the client through its extension request `_orca.dev/session/request_user_input`. ABB's ACP
client is non-interactive and does not declare the `orca.dev/interactionCapabilities`
`userInput` capability, so the question was cancelled and Orca failed the whole prompt
with `Internal error (-32603)`. The relay declares `userInput` on `initialize` and answers
each user-input request itself with Orca's `chat` outcome: "No user is available to answer
questions in this session. Proceed with reasonable assumptions and state them in your
answer." Orca returns that to the model as an ordinary tool result
(`{"answers": {}, "chat": ...}`) and the turn continues. All other messages pass through
unchanged.

Orca runs its tools itself inside the container. The launcher sets `umask 0` so
directories the agent creates in ABB's host-owned workspace can be removed after the run.

Known noise: after each turn Orca starts a tool-less auto-memory extraction request
(`AUTO_MEMORY_EXTRACTOR_V2`). When ABB closes the session it is cut off and recorded as
`llm_error: Client disconnected.`; the turn result is unaffected.
