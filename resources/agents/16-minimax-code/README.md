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
permission may receive allow-once; permanent grants are never selected. The outer `network/rules.toml` declares native catalog and content-review
endpoints plus local token-count compatibility. Arbitrary external tool endpoints
remain blocked; see [network adaptation](network/README.md). The profile selects Coding Maintenance from the
live KUMA catalog, with self-contained local tasks and one initial input.

The Agent receives an intercepted surrogate model key; real OpenRouter and KUMA
keys remain controlled by BBA. The native content-review service also requires `MAVIS_ACCESS_TOKEN` in the local
`.env`; an OpenRouter model key does not replace that login credential. Missing
native credentials fail before execution. Configure the host model using BBA's existing
`--model` / `OPENROUTER_MODEL`. This deployment is adapting until real Case, Agent,
Judge and host evidence acceptance all complete; image construction and handshake
alone do not certify it.
