# Claurst ACP deployment

This unit installs the pinned [Claurst](https://github.com/Kuberwastaken/claurst)
release `0.1.7` (tag `v0.1.7`, commit `0f5d970b`) — a Rust clean-room,
Claude-Code-style terminal coding agent — as the upstream prebuilt Linux binary and
runs its built-in ACP server (`claurst acp`, README "Editor integration";
`src-rust/crates/acp`). ABB invokes it over ACP stdio and keeps each Case in a
separate empty workspace. No upstream source is vendored or modified.

**Licence:** Claurst is GPL-3.0. This unit only downloads and runs the unmodified
upstream release binary inside the evaluation image; nothing from Claurst is
redistributed in this repository.

The acceptance profile uses Zhipu GLM's OpenAI-compatible coding endpoint.
Supply these variables only at runtime:

- `GLM_API_BASE_URL`: the OpenAI-style base URL, e.g.
  `https://open.bigmodel.cn/api/coding/paas/v4`.
- `GLM_MODEL`: the exact provider model ID, such as `glm-5.1`.
- `GLM_API_KEY`: the Bearer credential. It is never written into this unit.

The interception manifest admits only the tested route:
`POST https://open.bigmodel.cn/api/coding/paas/v4/chat/completions`.
A different OpenAI-compatible provider needs an explicit reviewed route update;
changing environment variables alone does not broaden container egress.

## Distribution

`install/distribution.json` pins `claurst-linux-x86_64.tar.gz` from the `v0.1.7`
GitHub release by sha256 (`0f7decc0…7f71f22`, the value published in the release's
`SHA256SUMS`). The Dockerfile downloads the archive, checks it with
`sha256sum -c`, and installs the single `claurst` binary to `/opt/claurst/bin`.
The binary needs GLIBC 2.39 and `libasound.so.2`, so the image is based on
`node:24-trixie` (Debian 13, GLIBC 2.41) with `libasound2t64`. Debian 13's
`useradd` creates home directories with mode 0700, so `/home/agent` is reset to
0755 and the workspace to 0777, keeping both usable by whichever unprivileged uid
the runtime selects.

## Launcher behavior

`bootstrap/launch.py` validates the three variables (HTTPS base URL without query
or fragment) and prepares, for every Case, a disposable `HOME` and `CLAURST_HOME`
under `/tmp`. It writes `settings.json` there with:

- `provider = "custom-openai"` and `providers.custom-openai.api_base =
  $GLM_API_BASE_URL`. Claurst's generic OpenAI-compatible provider uses the base URL
  verbatim and posts to `<base>/chat/completions`, exactly the admitted route. (The
  built-in `zhipu` provider appends `/v1` to an overridden base, which does not
  match the GLM coding endpoint.) The key is passed as `CUSTOM_OPENAI_API_KEY` in the
  child environment, not written to the file;
- `config.model = $GLM_MODEL`. Claurst silently falls back to default settings
  (the Anthropic provider) when `settings.json` does not deserialize, and its
  `config` object has no serde defaults, so every required field is written with its
  default value.

It also sets `CLAURST_DISABLE_MODELS_FETCH=1` (skips the startup refresh of
`https://models.dev/api.json`) and `CLAURST_DISABLE_NONESSENTIAL_TRAFFIC=1`.

### ACP relay: WebFetch/WebSearch permission

Claurst's built-in `WebFetch` and `WebSearch` tools contact arbitrary hosts. With
only the model route admitted, a fetch fails as `egress_denied` and the
interceptor rejects the whole trace. Settings `permissionRules` deny entries are
not consulted on the ACP path at the pinned release
(`ToolContext::request_permission_inner` asks the ACP client directly), so the
launcher runs `claurst acp` as a child and relays ACP stdio line by line; a
`session/request_permission` whose title is `Tool 'WebFetch' requires approval` or
`Tool 'WebSearch' requires approval` is answered by the relay with the agent's own
`reject_once` option. The tool then fails with `Permission denied by user`, which is
reported in the normal `tool_call_update`. All other messages, including every
other permission request, pass through unchanged to ABB.

## Known behavior

- Tool calls (Write, Edit, Bash, …) run natively in the container and each
  mutating call is routed through ACP `session/request_permission`.
- When the provider call fails, the ACP turn ends with `stopReason: "refusal"`
  rather than an error (observed with a missing credential during bring-up).
- The model sometimes calls Claurst's `StructuredOutput` tool at the end of a
  turn; it is part of the upstream tool set.

## Installation inputs

Tracked installation manifests live in install/. Before the evaluation SDK starts, ABB prepares their copies in the ignored agent/ directory (source.method = install). Docker builds use those generated copies. Do not edit agent/; edit install/ instead. If an existing copy differs, move agent/ aside and rerun to regenerate it.
