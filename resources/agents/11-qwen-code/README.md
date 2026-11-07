# Qwen Code ACP deployment

This unit installs the pinned [Qwen Code](https://github.com/QwenLM/qwen-code)
release `0.24.2` (tag `v0.24.2`, commit `1026c4a5`) from npm and runs its built-in
ACP server (`qwen --acp`). ABB invokes it over ACP stdio and keeps each Case in a
separate empty workspace. No upstream source is vendored or modified.

This deployment uses Qwen models through the standard Alibaba Cloud DashScope
API in China (Beijing). Get an API key from [Alibaba Cloud Bailian](https://bailian.console.aliyun.com/).
Set these variables in the repository's `.env`:

```dotenv
DASHSCOPE_API_KEY=
QWEN_API_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen3-coder-plus
```

Only `DASHSCOPE_API_KEY` is required. The launcher uses the URL and model above
when their variables are absent or empty. The model must be available to your
account. This is the standard API endpoint, not the separate Coding Plan endpoint.

`bootstrap/launch.py` starts `qwen --acp --auth-type openai --model $QWEN_MODEL`,
mapping the settings to Qwen Code's native `OPENAI_API_KEY`, `OPENAI_BASE_URL`
and `OPENAI_MODEL`. Here `openai` denotes the compatible protocol; the provider
is DashScope and the model is Qwen. Credentials are passed through the environment,
never command-line arguments. GLM credentials are not used by this unit.

The interception manifest admits:
`POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions`.
International regions and Coding Plan require matching credentials, endpoint and
interception route changes; changing environment variables alone does not broaden
egress. See [Qwen Code authentication](https://qwenlm.github.io/qwen-code-docs/en/users/configuration/auth/).

## Launcher behavior

`agent/` holds only a `package.json` and `package-lock.json` that pin
`@qwen-code/qwen-code@0.24.2`; the image installs it with `npm ci`, so the
registry tarball integrity is checked and no upstream file is edited.

For every Case the launcher creates a disposable `HOME` under `/tmp` and writes
`~/.qwen/settings.json` there before starting ACP. This keeps Qwen's state writable
by whichever unprivileged uid the runtime chooses and isolates Cases. The settings:

- disable usage statistics and telemetry (`privacy.usageStatisticsEnabled`,
  `telemetry.enabled`, plus `QWEN_USAGE_STATISTICS_ENABLED=false`). Upstream sends
  them to a third-party RUM endpoint, which the interceptor otherwise rejects as
  undeclared egress;
- disable auto-update;
- disable managed auto-memory and auto-dream. Both start an extra background
  model call after a turn, which the one-shot worker interrupts when it closes ACP.

Qwen Code can still abandon an in-flight streaming request on its own and retry
it; the interceptor records those as native `Client disconnected` transport errors.
They are not required calls and do not affect host acceptance.

## Installation inputs

Tracked installation manifests live in install/. Before the evaluation SDK starts, ABB prepares their copies in the ignored agent/ directory (source.method = install). Docker builds use those generated copies. Do not edit agent/; edit install/ instead. If an existing copy differs, move agent/ aside and rerun to regenerate it.
