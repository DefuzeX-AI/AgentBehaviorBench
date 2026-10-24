# kimchi ACP deployment

This unit installs the pinned [kimchi](https://github.com/getkimchi/kimchi) release
`v1.21.0` (GitHub release binary, sha256-verified) and runs its built-in ACP server
(`kimchi --mode acp`, `src/modes/acp/server.ts`). ABB invokes it over ACP stdio and keeps
each Case in a separate empty workspace. No upstream source is vendored or modified.

kimchi is Cast AI's terminal coding agent built on the Pi coding-agent SDK
(`@earendil-works/pi-coding-agent` 1.3.0). By default it talks to the hosted Kimchi LLM
gateway; this deployment configures no Kimchi account and instead registers the selected
OpenAI-compatible model as a Pi `models.json` custom provider, which kimchi keeps beside
its own (here empty) `kimchi-dev` provider.

The recorded source revision `65dfefb1` is the default-branch commit imported on
2026-10-24. It is one commit after tag `v1.21.0` (`52225d42`), the commit the release
binary was built from. That commit (getkimchi/kimchi#1525) refactors the documents
extension and its bundling step (`src/extensions/documents/`, `scripts/copy-resources.js`)
and edits comments in `src/shared/skill-discovery/resolve-skill-roots.ts`.

## Licence

Apache-2.0 (`LICENSE` and `"license": "Apache-2.0"` in `package.json`). The unit only
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

Pi's `openai-completions` API posts to `<baseUrl>/chat/completions`, which is the exact
route the runtime admits.

## Installation

`install/distribution.json` pins the `v1.21.0` release archives for `linux/amd64` and
`linux/arm64` with the SHA-256 digests published in the release's `checksums.txt`. The
Dockerfile selects the archive for the build architecture (`dpkg --print-architecture`),
verifies it with `sha256sum -c` and extracts `bin/kimchi` and `share/kimchi/` (themes,
export templates and bundled skills, which kimchi resolves next to its binary) into
`/opt/kimchi`. The binary is a self-contained Bun executable, so no Node toolchain or npm
lock is needed. kimchi is not published on npm (`@kimchi-dev/cli` is a private
workspace name), and a source build needs pnpm, Bun and the Go proxy helper, so the
release binary is used.

`ripgrep`, `fd` (Debian `fd-find`, linked as `fd`) and `git` are installed from Debian.

## Launcher behavior

`bootstrap/launch.py` validates the three variables (HTTPS base URL without query or
fragment), creates a disposable `HOME` under `/tmp` for every Case and `exec`s
`/opt/kimchi/bin/kimchi --mode acp`, which owns the ACP stdio channel directly. kimchi
derives its configuration and agent directory (`~/.config/kimchi/harness`) from `HOME`,
so the disposable home keeps config, sessions and memory writable by whichever
unprivileged uid the runtime chooses and isolates Cases. It writes:

- `harness/models.json`: one provider `abb` (`api = "openai-completions"`,
  `baseUrl` = `ABB_AGENT_MODEL_BASE_URL`) with one model `ABB_AGENT_MODEL`, and
  `apiKey = "$ABB_AGENT_MODEL_API_KEY"`, which Pi resolves from the environment at
  request time, so the key never appears in argv or on disk;
- `harness/settings.json`: `defaultProvider`/`defaultModel` selecting that model (ACP
  `session/new` does not choose one), every kimchi multi-model role (`orchestrator`,
  `planner`, `builder`, `reviewer`, `explorer`, `researcher`) pinned to it so delegation
  never targets a Kimchi-hosted default, and Pi install telemetry off;
- `config.json`: no Kimchi API key, telemetry off, and the first-run skill-path and
  migration prompts answered.

It also sets `KIMCHI_TELEMETRY_ENABLED=0`, `KIMCHI_NO_UPDATE_CHECK=1`, `PI_OFFLINE=1`,
`PI_SKIP_VERSION_CHECK=1`, `PI_TELEMETRY=0` and `MEM0_TELEMETRY=false`, and removes
`KIMCHI_API_KEY`, `CASTAI_API_KEY`, `OPENROUTER_API_KEY` and `KIMCHI_BASE_URL` from the
child environment. Without a Kimchi key kimchi makes no model-metadata, billing or
organization-policy request, and the Kimchi-hosted `web_search` tool (it posts to the
Kimchi gateway with the account key) returns an error instead of searching.

## Tools and permissions

The model is offered 25 tools: `read`, `write`, `edit`, `ls`, `find`, `grep`, `bash`,
`bash_control`, `create_todos`, `update_todos`, `add_todo`, `mark_todo`, `confirm_todos`,
`clear_todos`, `set_phase`, `submit_plan`, `list_ferments`, `Agent` (in-container subagents on
the same model), `skill_view`, `list_models`, `set_model`, `questionnaire`, `web_fetch`,
`web_search` and `dispatch_to_cloud_agent`. In this deployment `web_search` and
`dispatch_to_cloud_agent` need a Kimchi account and fail, `questionnaire` reports that no
interactive UI is attached, `web_fetch` reaches only hosts the egress observer allows (the
package registries), and `list_models`/`set_model` see only the selected model.
`requirement.md` describes this surface.

ACP sessions start in kimchi's `default` permissions mode. File writes, edits and shell
commands send ACP `session/request_permission`, which ABB answers with its `allow_once`
policy. Shell commands run natively inside the container; kimchi did not use client
terminals or client file-system methods in the acceptance run.

## Known non-blocking noise

kimchi streams fine-grained ACP updates (one `agent_message_chunk` or `tool_call_update` per
model delta) plus `_kimchi.dev/pi_notify` status notifications. A one-step Case therefore
produces several hundred kilobytes of `framework.jsonl`, which exceeds the local Judge's
default `ABB_LOCAL_JUDGE_MAX_CHARS` (120000) and makes it report `inconclusive` for evidence
size alone. Raise that limit for `--sdk local` runs; it does not affect execution or evidence
capture.

## Installation inputs

Tracked installation manifests live in install/. Before the evaluation SDK starts, ABB prepares their copies in the ignored agent/ directory (source.method = install). Docker builds use those generated copies. Do not edit agent/; edit install/ instead. If an existing copy differs, move agent/ aside and rerun to regenerate it.

## Validation scope

The acceptance record describes one shared provider/model combination. It does not
certify every shared provider/model combination; run a fresh Case after changing it.
