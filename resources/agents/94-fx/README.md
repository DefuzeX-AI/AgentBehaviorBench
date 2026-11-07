# fx ACP deployment

This unit installs the pinned [fx](https://github.com/vercel-labs/fx) release `0.0.14`
(tag `v0.0.14`, commit `1a070af3`, Apache-2.0) as the upstream prebuilt, statically
linked Linux binary and runs its built-in ACP server (`fx acp`). ABB invokes it over ACP
stdio and keeps each Case in a separate empty workspace. No upstream source is vendored
or modified.

This unit uses default model selection; no `[model]` declaration is needed. ABB passes
the resolved configuration through `ABB_AGENT_MODEL_API_KEY`, `ABB_AGENT_MODEL_BASE_URL`
and `ABB_AGENT_MODEL`; the runtime admits the exact `POST <selected-base>/chat/completions`
route.

## Distribution

`install/distribution.json` pins `fx-linux-x86_64.tar.gz` from the `v0.0.14` GitHub
release by sha256 (`731c1914…94455a8548b`, the release's `.sha256` asset). The
Dockerfile downloads it, checks it with `sha256sum -c`, installs the `fx` binary to
`/opt/fx/bin/fx` and runs `--version`.

## Launcher behavior

`bootstrap/launch.py` validates the model variables (HTTPS base URL without query or
fragment), creates a disposable `HOME` per Case, writes `~/.fx/settings.json` and runs
`fx acp` as a child. The settings select one custom model connection
([custom model connections](https://fx.sh/docs/configure-fx/custom-model-connections)):

```json
{
  "provider": "abb",
  "models": {"abb": "<model>"},
  "providers": {
    "abb": {
      "protocol": "openai-chat-completions",
      "base_url": "http://127.0.0.1:<relay port>/v1",
      "auth": {"type": "bearer", "env": "FX_ABB_API_KEY"}
    }
  }
}
```

The key is passed only in `FX_ABB_API_KEY`, which fx reads at request time; the file
holds no secret and `ABB_AGENT_MODEL_API_KEY` is removed from fx's environment. The
launcher also sets `FX_AUTO_UPGRADE=0` and `FX_DISABLE_KEYCHAIN=1`.

**Model relay (`bootstrap/model_relay.py`).** fx's HTTP client does
not use `HTTPS_PROXY`, so the connection points at a plain-HTTP relay on an ephemeral
`127.0.0.1` port (added to `NO_PROXY`). fx sends `POST <base_url>/chat/completions`; the
relay sends each `POST /v1/chat/completions` as `POST <selected-base>/chat/completions`
through the runtime's `HTTPS_PROXY` with Python's default TLS context and streams the
response back unchanged; anything else gets a local 404. Every model call is still
intercepted and recorded.

**Permissions.** fx keeps its default `auto` permission mode: routine project work
(editing workspace files, running tests) runs without asking, and other actions are
first checked by fx's model-based safety review (the same connection and model), which
can hold the action. When fx does ask over ACP, ABB answers with its `allow_once`
policy. fx runs commands in its own shell process inside the workspace, not through
ABB's ACP terminal. The launcher sets `umask 0` so directories the agent creates can be
removed by the host after the Case.

No egress denials were observed in the smoke run: fx's only network traffic in this
deployment is the model connection.
