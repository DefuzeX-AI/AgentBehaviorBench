# maki ACP deployment

This unit installs the pinned [maki](https://github.com/tontinton/maki) release `0.6.4`
(tag `v0.6.4`, commit `621ef0c4`, MIT) as the upstream prebuilt static Linux binary and runs
its built-in ACP server (`maki acp`). ABB invokes it over ACP stdio and keeps each Case in a
separate empty workspace. No upstream source is vendored or modified.

This unit uses default model selection; no `[model]` declaration is needed. ABB passes
the resolved configuration through `ABB_AGENT_MODEL_API_KEY`, `ABB_AGENT_MODEL_BASE_URL`
and `ABB_AGENT_MODEL`; the runtime admits the exact `POST <selected-base>/chat/completions`
route.

## Distribution

`install/distribution.json` pins `maki-v0.6.4-x86_64-unknown-linux-musl.tar.gz` from the
`v0.6.4` GitHub release by sha256 (`1c02315b…bd94e87a`, the release's `sha256sums.txt`
entry). The Dockerfile downloads it, checks it with `sha256sum -c` and installs the single
`maki` binary to `/opt/maki/bin`.

## Launcher behavior

`bootstrap/launch.py` validates the model variables (HTTPS base URL without query or
fragment), creates a disposable `HOME` per Case and execs:

```
maki acp --model deepseek/<model>
```

with `DEEPSEEK_BASE_URL=<base>` and `DEEPSEEK_API_KEY=<key>`. `deepseek/` selects maki's
bundled OpenAI-compatible DeepSeek provider, `<SLUG>_BASE_URL` is maki's documented endpoint
override (`maki-config/src/providers.rs` `base_url_env_var`), and the provider sends
`POST <base>/chat/completions`. The key is never on the command line or on disk. maki's
default permission behavior is kept: commands and edits are requested through
`session/request_permission`, which ABB answers with its `allow_once` policy. The launcher
sets `umask 0` so directories the agent creates in ABB's host-owned workspace can be removed
after the run.

Known noise: at startup maki fetches the models.dev catalog and lists the provider's models
(`GET <base>/models`); both are refused by the egress policy (one denial each) and maki
continues with its bundled catalog. The turn is unaffected.
