# minimax-code ACP deployment

Source: https://github.com/MiniMax-AI/minimax-code at `a5639bcc6146754e01f1ae18bb88545f18299fd6`.
The imported checkout is local and ignored by the parent repository; recover it
inside this directory with:

```bash
git clone https://github.com/MiniMax-AI/minimax-code agent
git -C agent checkout a5639bcc6146754e01f1ae18bb88545f18299fd6
```

`agent.toml` selects the outer bootstrap, which execs the native stdio command. The Dockerfile builds the pinned
source with its upstream package lock. Generic BBA staging installs the ACP Python
requirements, and the KUMA overlay installs the evaluation SDK. Do not build the
outer Dockerfile directly without BBA's injected runtime directory.

The non-root user owns `/home/agent` and `/home/agent/workspace`. Case containers
isolate workspace, native session and local configuration. Tools requesting ACP
permission may receive allow-once; permanent grants are never selected.

ACP uses BBA's native observation path. The native command selects its own model,
endpoint and authentication. BBA records redacted traffic without substituting a
model key or providing local token-count replies. `--model` / `OPENROUTER_MODEL`
do not select this Agent's model. The outer `network/rules.toml` scopes catalog
and content-review access; unknown destinations remain blocked. See
[network adaptation](network/README.md).

This unit uses the CN MiniMax API-key mode. Put `MINIMAX_API_KEY` in the host
`.env`. The runtime requires it before starting the container, then forwards the
real key unchanged. `bootstrap/native-config.yaml` selects
`https://api.minimax.cn/anthropic` and the native `minimax/MiniMax-M3` model.
`bootstrap/launch.py` creates a private profile and calls the upstream CLI's
`provider set-minimax-key --api-key-env MINIMAX_API_KEY` before exec'ing ACP.
Setup output cannot contaminate JSON-RPC stdout. No key is baked into the image,
passed in arguments or saved in the shared results directory. Upstream source is
unmodified; configuration is through the native CLI and native file format.

This model path needs no MiniMax account login or MAVIS_ACCESS_TOKEN. Managed
search, connectors and other account services may still require separate login;
they are not provisioned by this deployment. API permission and available quota
must be checked by a real model request; saving a key is not authentication proof.

The profile selects Coding Maintenance from the KUMA catalog, with self-contained
local tasks and one initial input. Image construction, handshake and proxy tests
do not certify this deployment; native Case, Agent, Judge and host evidence
acceptance must complete before changing the registry to `ready`.

Offline acceptance (requires a BBA-staged image tagged as below; run from the
repository root):

```bash
docker run --rm --network=none -i \
  -e MINIMAX_API_KEY=offline-fixture-not-a-real-key -e MAVIS_REGION=cn \
  abb-acp-acceptance/minimax-code:source python - \
  < tests/acp_fixtures/minimax_byok_handshake.py
```

This verifies native API-key selection, private configuration and ACP session
creation, without validating the key or making a model request.
