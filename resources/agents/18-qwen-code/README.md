# Qwen Code ACP deployment

This unit installs the pinned [Qwen Code](https://github.com/QwenLM/qwen-code)
release `0.24.2` (tag `v0.24.2`, commit `1026c4a5`) from npm and runs its built-in
ACP server (`qwen --acp`). ABB invokes it over ACP stdio and keeps each Case in a
separate empty workspace. No upstream source is vendored or modified.

The acceptance profile uses Zhipu GLM's OpenAI-compatible coding endpoint.
Supply these variables only at runtime:

- `GLM_API_BASE_URL`: the OpenAI-style base URL, e.g.
  `https://open.bigmodel.cn/api/coding/paas/v4`.
- `GLM_MODEL`: the exact provider model ID, such as `glm-5.1`.
- `GLM_API_KEY`: the Bearer credential. It is never written into this unit.

`bootstrap/launch.py` validates the three variables and starts
`qwen --acp --auth-type openai --model $GLM_MODEL`, passing the credential and base
URL through Qwen Code's native `OPENAI_API_KEY` / `OPENAI_BASE_URL` environment
variables rather than command-line arguments.

The interception manifest admits only the tested route:
`POST https://open.bigmodel.cn/api/coding/paas/v4/chat/completions`.
A different OpenAI-compatible provider needs an explicit reviewed route update;
changing environment variables alone does not broaden container egress.

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
