# minimax-code ACP deployment

Source: https://github.com/MiniMax-AI/minimax-code at `a5639bcc6146754e01f1ae18bb88545f18299fd6`.
The imported checkout is local and ignored by the parent repository; recover it
inside this directory with:

```bash
git clone https://github.com/MiniMax-AI/minimax-code agent
git -C agent checkout a5639bcc6146754e01f1ae18bb88545f18299fd6
```

`agent.toml` selects the native stdio command. The Dockerfile builds the pinned
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

A usable native MiniMax login still needs to be provisioned inside the isolated
runtime. The optional `MAVIS_ACCESS_TOKEN` declaration forwards an existing value
unchanged for native operations that read it; it is not a substitute for the
CLI's complete managed-login flow. An OpenRouter key cannot authenticate MiniMax.
BBA no longer rejects startup merely because this optional variable is absent.
The native Agent decides whether it can proceed, and native failures are recorded.

The profile selects Coding Maintenance from the KUMA catalog, with self-contained
local tasks and one initial input. Image construction, handshake and proxy tests
do not certify this deployment; native Case, Agent, Judge and host evidence
acceptance must complete before changing the registry to `ready`.
