# QwenPaw ACP deployment

This unit runs [QwenPaw](https://github.com/agentscope-ai/QwenPaw) (`agentscope-ai/QwenPaw`,
revision `27d22cd1`) through its native ACP server (`qwenpaw acp`). ABB drives one ACP session
per Case; follow-up inputs reuse that session. `source.method = "git"` restores the pinned
checkout into `agent/`; no upstream file is modified.

This unit uses default model selection; no `[model]` declaration is needed. ABB passes the
resolved configuration through `ABB_AGENT_MODEL_API_KEY`, `ABB_AGENT_MODEL_BASE_URL` and
`ABB_AGENT_MODEL`, and the runtime admits the `POST <selected-base>/chat/completions` route.

## Image

The pinned checkout is installed into `/opt/qwenpaw-venv` (with `setuptools<82`), separate from
the interpreter that runs the ABB worker. The venv is deliberately not on `PATH`; the launcher
execs `/opt/qwenpaw-venv/bin/qwenpaw` by absolute path. `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1`:
browser automation is not part of this deployment.

## Launcher (`install/abb-acp-launch.py`)

Copied into `agent/abb-acp-launch.py` by source preparation. It validates the three model
variables (HTTPS base URL without query or fragment) and uses QwenPaw's headless provider
`qwenpaw acp --runtime-provider openai-env` (`src/qwenpaw/cli/acp_cmd.py`,
`agents/acp/runtime_provider.py`), which reads `OPENAI_BASE_URL`, `OPENAI_API_KEY` and
`OPENAI_MODEL`. QwenPaw keeps its config, agent workspace (AGENTS.md, memory) and secrets under
`QWENPAW_WORKING_DIR`; the launcher points `HOME`, `QWENPAW_WORKING_DIR`, `QWENPAW_SECRET_DIR`
and `QWENPAW_BACKUP_DIR` at a disposable directory per Case, so nothing carries across Cases.
Tool Guard and the permission policy keep upstream defaults (`permission_policy = "allow_once"`).

## Workspace fixture

`evaluation/fixture/` is a small project the Cases can work in: `build.bat` (CRLF line endings,
required by `cmd.exe`), `legacy.ini` (ISO-8859-1), `worker.sh` (a background worker that loops
until killed) and a `README.md` describing them. `adapter.cwd` equals
`evaluation.workspace.path` (`/workspace/project`).

## Scope

Channel integrations (DingTalk, Lark, Discord, Telegram, …), cron tasks, console and desktop
frontends, plugins and browser automation are out of scope, as stated in `requirement.md`.
