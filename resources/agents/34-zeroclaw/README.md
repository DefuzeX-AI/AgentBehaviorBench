# ZeroClaw ACP deployment

This unit installs the pinned [ZeroClaw](https://github.com/zeroclaw-labs/zeroclaw)
release `v0.8.5` (commit `cb2b20a9`) from its sha256-checked GitHub release
archive (`zeroclaw-x86_64-unknown-linux-gnu.tar.gz`) and drives its built-in ACP
server (`zeroclaw acp`) over stdio. No upstream source is vendored or modified.

License: `MIT OR Apache-2.0` (the workspace `Cargo.toml`, `LICENSE-MIT`,
`LICENSE-APACHE`).

ZeroClaw is a general-purpose personal assistant runtime (not a coding agent),
so the profile selects KUMA's `basic-safety-general` strategy group.

The acceptance profile uses Zhipu GLM's OpenAI-compatible coding endpoint.
Supply these variables only at runtime:

- `GLM_API_BASE_URL`: the OpenAI-style base URL, e.g.
  `https://open.bigmodel.cn/api/coding/paas/v4`.
- `GLM_MODEL`: the exact provider model ID, such as `glm-5.1`.
- `GLM_API_KEY`: the Bearer credential. It is never written into this unit.

The interception manifest admits only the tested model route:
`POST https://open.bigmodel.cn/api/coding/paas/v4/chat/completions`.
A different OpenAI-compatible provider needs an explicit reviewed route update;
changing environment variables alone does not broaden container egress.

## Launcher

`bootstrap/launch.py`:

1. validates the three `GLM_*` variables (HTTPS base URL, no query/fragment);
2. creates a disposable `HOME` under `/tmp` and writes
   `$HOME/.zeroclaw/config.toml` (schema v3) there, so ZeroClaw's config,
   SQLite ACP session store, runtime trace and audit log are writable by
   whichever unprivileged uid the runtime selects and isolated per Case;
3. passes the key through ZeroClaw's schema-mirror environment override
   `ZEROCLAW_providers__models__custom__abb__api_key`, so it is never written to
   disk or placed in argv; the original `GLM_API_KEY` is not forwarded;
4. runs `zeroclaw --config-dir $HOME/.zeroclaw acp` as a child and relays ACP
   stdio (see "Permission options" below).

## Config choices

- Provider `[providers.models.custom.abb]` (ZeroClaw's catch-all
  OpenAI-compatible slot) with `uri = $GLM_API_BASE_URL`, `model = $GLM_MODEL`,
  `wire_api = "chat_completions"` and `native_tools = true`. Without
  `native_tools` the `custom` slot uses ZeroClaw's prompt-guided text fallback
  (tool calls as `<tool_call>` text, no `tools` array in the request). GLM
  supports OpenAI function calling, so the default `auto` dispatcher then sends
  real tool schemas and receives structured `tool_calls`. In the first KUMA
  trial without it, GLM once wrote fabricated `<function_results>` text instead
  of a `<tool_call>` block, so nothing ran while the reply claimed files were
  written.
- One agent `[agents.abb]` (auto-selected by ACP `session/new` as the sole
  configured agent) bound to risk profile `abb` and runtime profile `abb`.
- Risk profile `abb`: `level = "supervised"`, `workspace_only = true`, and
  otherwise upstream defaults (command allowlist, forbidden paths, blocking of
  high-risk commands, auto-approved read-only tools). File writes/edits and shell
  commands therefore reach the ACP client as `session/request_permission`;
  ABB answers `allow_once`. The ACP session `cwd` (`/home/agent/workspace`) is
  the file/shell boundary.
- `browser`, `http_request`, `web_fetch` and `web_search` are disabled: they
  would be egress outside the admitted route, and the profile states that no
  web access exists. The remaining built-in tools are ZeroClaw's defaults.
- ACP sessions never use ZeroClaw's long-term memory tools (upstream design).

## Permission options

For `file_write`/`file_edit` approvals ZeroClaw adds a non-standard
`reject_with_edit` option (kind `reject_with_edit`) next to the four standard
ACP kinds. The ACP Python SDK used by ABB rejects the whole
`session/request_permission` request on that unknown enum value, so the write
would be refused by a protocol error instead of a permission decision. The
launcher's stdout relay drops only options whose `kind` is not an ACP
`PermissionOptionKind`; every standard option, the tool call and ZeroClaw's own
approval handling are unchanged. All other ACP traffic is relayed unchanged.

## Observed network

In the validation runs the only container egress was the admitted GLM route.
ZeroClaw's gateway update check applies only to `zeroclaw daemon`/`gateway`,
which this unit never starts. `network/rules.toml` therefore declares no extra
routes.

## Known non-blocking notes

- ZeroClaw streams `agent_thought_chunk` updates (GLM reasoning); ABB records
  them as protocol events. The final answer is the `agent_message_chunk` text.
- ZeroClaw's tool updates carry extra `name`/`body` fields and the prompt
  result carries an extra `content` string (documented ZeroClaw extensions);
  the ACP client ignores them.
- GLM's coding endpoint may report a different served model name (for example
  `glm-5.3`) in responses than the `glm-5.1` requested.

## Installation inputs

Tracked installation manifests live in install/. Before the evaluation SDK starts, ABB prepares their copies in the ignored agent/ directory (source.method = install). Docker builds use those generated copies. Do not edit agent/; edit install/ instead. If an existing copy differs, move agent/ aside and rerun to regenerate it.
