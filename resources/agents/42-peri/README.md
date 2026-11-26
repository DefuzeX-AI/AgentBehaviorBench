# Peri ACP deployment

This unit installs the pinned [Peri](https://github.com/KonghaYao/peri) release `4.3.0`
(tag `agent-v4.3.0`, commit `e598d178`, Apache-2.0) as the upstream prebuilt Linux binary
with its bundled `peri-resources` directory, and runs its built-in ACP server (`peri acp`).
ABB invokes it over ACP stdio and keeps each Case in a separate empty workspace. No upstream
source is vendored or modified.

This unit uses default model selection; no `[model]` declaration is needed. ABB passes
the resolved configuration through `ABB_AGENT_MODEL_API_KEY`, `ABB_AGENT_MODEL_BASE_URL`
and `ABB_AGENT_MODEL`; the runtime admits the exact `POST <selected-base>/chat/completions`
route.

## Distribution

`install/distribution.json` pins `peri-linux-x86_64.tar.gz` from the `agent-v4.3.0` GitHub
release by sha256 (`33545b37…a6a72ba8`, the release's `.sha256` file). The Dockerfile
downloads it, checks it with `sha256sum -c` and unpacks `peri` and `peri-resources/` to
`/opt/peri/bin`. Peri's workflows need Node.js, which is not installed; the core agent and
its tools do not use it.

## Launcher behavior

`bootstrap/launch.py` validates the model variables (HTTPS base URL without query or
fragment), creates a disposable `HOME` per Case and runs:

```
peri acp --settings-stdin --cwd <workspace>
```

`--settings-stdin` makes Peri read a 4-byte big-endian length and a settings JSON object
from stdin before ACP begins (`peri-acp` `host/stdio` `read_bootstrap_settings`). The
launcher writes that preamble, then relays ABB's ACP stdin unchanged; Peri's stdout is the
ACP channel directly. The settings declare one provider `abb` of type `openai` with the
selected base URL and key, map every model tier to the selected model and make the `opus`
profile active. Peri then sends `POST <base>/chat/completions`. The key therefore reaches
Peri through the pipe only: it is not written to disk, not on the command line, and
`ABB_AGENT_MODEL_API_KEY` is removed from Peri's environment.

Peri's default permission behavior (tool calls auto-approved) is kept. It runs its tools
itself inside the container. The launcher sets `umask 0` so directories the agent creates in
ABB's host-owned workspace can be removed after the run.

Known noise: after a turn Peri starts one tool-less request (a background summary). When ABB
closes the session it is cut off and recorded as `llm_error: connection closed`; the turn is
unaffected.
