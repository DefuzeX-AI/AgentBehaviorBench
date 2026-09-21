# GitHub Copilot CLI ACP deployment

This unit installs the pinned [GitHub Copilot CLI](https://github.com/github/copilot-cli)
release `1.0.86` (tag `v1.0.86`, commit `ab6139c6`; the npm package's
`buildMetadata.gitCommit` is `615005b5`) from npm and runs its built-in ACP server
(`copilot --acp --no-auto-update`). ABB invokes it over ACP stdio and keeps each Case
in a separate empty workspace.

> **License caveat — proprietary, not open source.** `@github/copilot` declares
> `"license": "SEE LICENSE IN LICENSE.md"`, and that file is the *GitHub Copilot CLI
> License* (install/run grant; redistribution only unmodified and as part of a larger
> application; no modification or derivative works). GitHub's repository metadata
> reports the license as `NOASSERTION`. The CLI itself is a closed native binary:
> `npm ci` downloads `@github/copilot` (a small Node loader) plus the platform package
> `@github/copilot-linux-x64` (~167 MB native executable) from the npm registry **at
> image build time**. Nothing from upstream is vendored in this unit or modified, and
> the built image must not be redistributed standalone.

The acceptance profile uses Zhipu GLM's OpenAI-compatible coding endpoint through
Copilot's BYOK provider support. No GitHub account, login or token is used. Supply
these variables only at runtime:

- `GLM_API_BASE_URL`: the OpenAI-style base URL, e.g.
  `https://open.bigmodel.cn/api/coding/paas/v4`.
- `GLM_MODEL`: the exact provider model ID, such as `glm-5.1`.
- `GLM_API_KEY`: the Bearer credential. It is never written into this unit.

## Launcher behavior

`agent/` holds only a `package.json` and `package-lock.json` that pin
`@github/copilot@1.0.86` (and, through the lock, the matching platform packages with
their registry integrity hashes); the image installs them with `npm ci`.

`bootstrap/launch.py` validates the three GLM variables and maps them onto Copilot's
documented environment contract (`copilot help environment`), never onto argv:

- `COPILOT_PROVIDER_BASE_URL`, `COPILOT_PROVIDER_API_KEY`,
  `COPILOT_PROVIDER_TYPE=openai`, `COPILOT_PROVIDER_WIRE_API=completions` — BYOK
  mode; upstream: "the CLI uses this provider instead of GitHub Copilot's model
  routing. GitHub authentication is not required."
- `COPILOT_MODEL=$GLM_MODEL` — ACP `session/new` does not choose a model, so GLM is
  selected at startup.
- `COPILOT_PROVIDER_MAX_PROMPT_TOKENS=128000`, `COPILOT_PROVIDER_MAX_OUTPUT_TOKENS=16384`
  — `glm-5.1` is not in Copilot's model catalog; without these the CLI warns and
  uses generic defaults.
- `COPILOT_OFFLINE=true` — skips GitHub authentication, telemetry, web tools, the
  GitHub MCP server and auto-update. Each of those would otherwise be network egress
  outside the declared route, which the interceptor rejects. `COPILOT_AUTO_UPDATE=false`
  and `--no-auto-update` are set as well.
- `COPILOT_GITHUB_TOKEN`, `GH_TOKEN` and `GITHUB_TOKEN` are removed from the child
  environment, and OTel export variables are dropped (Copilot only exports OTel when
  they are set).

For every Case the launcher creates a disposable `HOME` under `/tmp`, points
`COPILOT_HOME` and the XDG directories into it, and then `exec`s the agent. This keeps
Copilot's config and session state writable by whichever unprivileged uid the
runtime chooses and isolates Cases. It execs the native platform binary directly
(falling back to the npm loader), so no extra Node.js loader process stays resident
under the container's memory limit.

Tool permission requests are answered by ABB's ACP adapter (`allow_once`);
`COPILOT_ALLOW_ALL` is deliberately not set.

The interception manifest admits only the tested route:
`POST https://open.bigmodel.cn/api/coding/paas/v4/chat/completions`.
A different OpenAI-compatible provider needs an explicit reviewed route update;
changing environment variables alone does not broaden container egress.

## Known non-blocking noise

In the 3-step acceptance run, the interceptor recorded the final streamed model call
of steps 2 and 3 as `llm_error: Client disconnected.` The agent had already received
those responses: both steps completed and returned their full answers, and the
host still accepted the trace (`host_trace_validation: succeeded`, Judge `pass`).
Copilot appears to close the streaming connection itself once the final chunk has
arrived. These calls are not background title or summary requests, and there is no
switch to change this behavior. A single-step run (certification) produced no such
error.
