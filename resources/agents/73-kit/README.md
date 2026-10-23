# Kit ACP deployment

This unit installs the pinned [Kit](https://github.com/mark3labs/kit) release `0.136.0`
(tag `v0.136.0`, commit `c50c75cb`, MIT) as the upstream prebuilt Linux binary and runs
its built-in ACP server (`kit acp`). ABB invokes it over ACP stdio and keeps each Case in
a separate empty workspace. No upstream source is vendored or modified.

This unit uses default model selection; no `[model]` declaration is needed. ABB passes
the resolved configuration through `ABB_AGENT_MODEL_API_KEY`, `ABB_AGENT_MODEL_BASE_URL`
and `ABB_AGENT_MODEL`; the runtime admits the exact `POST <selected-base>/chat/completions`
route.

## Distribution

`install/distribution.json` pins `kit_0.136.0_linux_amd64.tar.gz` from the `v0.136.0`
GitHub release by sha256 (`b4955334…d235cf6`, the value in the release's
`checksums.txt`). The Dockerfile downloads it, checks it with `sha256sum -c` and installs
the single `kit` binary to `/opt/kit/bin`.

## Launcher behavior

`bootstrap/launch.py` validates the model variables (HTTPS base URL without query or
fragment), creates a disposable `HOME` per Case and execs:

```
kit acp --model openai/<model> --provider-url <base>
```

With these flags Kit sends `POST <base>/chat/completions` (verified against a local stub,
with and without a `/v1` suffix). With a custom provider URL Kit ignores
`OPENAI_API_KEY`, so the credential is passed as `KIT_PROVIDER_API_KEY`, Kit's
environment form of `--provider-api-key`; it is never on the command line or on disk.
Kit's default ACP approval mode (`ask`) is kept: edits, commands and sub-agents are
requested through `session/request_permission`, which ABB answers with its
`allow_once` policy. The launcher sets `umask 0` so directories the agent creates in
ABB's host-owned workspace can be removed after the run.
