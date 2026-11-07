# Octop ACP deployment

This unit installs the pinned [Octop](https://github.com/TencentCloud/Octop) release
`1.0.2` (tag `v1.0.2`, commit `dd9dce47`) from PyPI and runs its built-in inbound
ACP server (`octop acp`). ABB drives it over ACP stdio and keeps each Case in a
separate empty workspace. No upstream source is vendored or modified.

License: upstream `LICENSE` at the pinned commit is MIT.

This unit uses default model selection; no `[model]` declaration is needed. Configure
the selected provider in `.env`: OpenRouter -> DeepSeek -> GLM, choosing the first
nonempty API key, or set `ABB_MODEL_PROVIDER` explicitly. Supply the selected
provider's model name as well. See
[model selection](../../../docs/Model-Selection.md) for variables and constraints.

ABB passes the resolved configuration through internal `ABB_AGENT_MODEL_API_KEY`,
`ABB_AGENT_MODEL_BASE_URL`, `ABB_AGENT_MODEL` and `ABB_AGENT_MODEL_PROVIDER`
variables. Users do not fill these internal variables. Only the selected credential
reaches the launcher.

## Installation

`install/requirements.txt` pins `octop==1.0.2` and its full dependency closure with
hashes, generated for CPython 3.12 on x86_64 Linux:

```bash
echo 'octop==1.0.2' > in.txt
uv pip compile in.txt --python-version 3.12 --python-platform x86_64-manylinux_2_28 \
  --generate-hashes --no-annotate --output-file install/requirements.txt
```

The image installs it into its own venv (`/opt/octop`) with
`pip install --require-hashes --no-deps`. The ABB runtime venv (`/opt/venv`) stays
separate and only carries the OpenTelemetry and JSON-schema packages the worker
needs. The dashboard bundle that ships inside the wheel is unused; no Node stage is
built.

## Launcher behavior

`bootstrap/launch.py` prepares one disposable Octop home per Case and then hands
stdio to the ACP server:

1. recreate `$OCTOP_HOME` (default `/home/agent/.octop`) so no state crosses Cases;
2. `octop init --non-interactive` to create the SQLite control plane and an admin
   account (a local-only password; nothing authenticates against it in ACP mode);
3. `octop provider create --kind openai` with the runtime base URL, key and model
   id, so the harness calls the intercepted `<base_url>/chat/completions` route;
4. `octop agent create` and `octop agent start` for a single agent;
5. pin that agent's `config_json.workspace_dir` to `/home/agent/workspace` — the
   default would be `$OCTOP_HOME/agents/<id>`, where the Case files are invisible;
6. `exec octop acp --agent <id>`.

The model key reaches the provider row through the child environment only. It is
never written to argv or to a file outside the disposable home.

## Scope of the deployed assistant

Octop is a multi-user, multi-agent assistant platform; in ACP mode only the pieces
the harness needs are active. The dashboard, IM channels (Feishu, WeCom, DingTalk,
Discord), cron scheduler, knowledge bases, browser tools and MCP connectors are
present in the image but not configured, so a Case sees one agent with local file
and shell tools rooted at the workspace.

## Installation inputs

`install/requirements.txt` is the only install input; it is copied to `agent/` before
the image build and consumed by the `RUN` line above.

## Validation scope

The unit is validated with an ABB local Case (`--sdk local`, Docker). A Case checks
that the ACP handshake succeeds, that a prompt produces model traffic on the
intercepted route, and that file and shell tool calls are recorded in
`acp-events.jsonl`. Dashboard, channel and cron behavior are out of scope here.
