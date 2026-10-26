# WhipCode integration

This unit runs the pinned native WhipCode ACP adapter and its native daemon. The
launcher maps ABB's selected model into Whip's native configuration using an
environment-key reference. It does not rewrite ACP messages, prompts, tool
results or upstream source. Each Case gets its own daemon home; native shutdown
runs when the ACP process exits. Permissions use ACP `allow_once`.

## Manual source prerequisite

The pinned upstream revision contains `.claude/skills -> ../.agents/skills`, a
directory symlink that ABB's Git restoration and Docker staging do not support.
Consequently this unit deliberately uses `source.method = "bundled"`, not
unattended Git restoration. No inner `agent/` files are committed.

Clone the source outside this unit, check out the exact revision, and run the
provided manual preparation helper from the ABB root:

```sh
git clone https://github.com/context-labs/whip /tmp/whip-source-474
git -C /tmp/whip-source-474 checkout 1c5da05987d2869687dfc95fc9128ad2ad68e0f0
python resources/agents/127-whip/prepare_source.py /tmp/whip-source-474
```

The helper refuses an existing destination or dirty/wrong source (including ignored files). It checks that
links stay within the source tree, then materializes the internal link target
as ordinary files and verifies every copied file's bytes. It changes neither the
original checkout nor upstream business logic. Preserve any existing `agent/`
before preparing a replacement. Source preparation in a fresh ABB checkout
requires this manual step; configuration alone cannot restore it.

The Docker image compiles the unmodified source with the Go version declared by
its `go.mod`. Upstream supports a plain Go development build without its web
renderer; this deployment uses ACP and starts no web listener. Python, bash, git
and ripgrep are available for local coding tasks.

## Model and environment

Set ABB's normal shared model/provider variables on the host. The launcher reads
runtime-owned `ABB_AGENT_MODEL_API_KEY`, `ABB_AGENT_MODEL_BASE_URL` and
`ABB_AGENT_MODEL`; do not set these internal variables in a project `.env`.
The provider must support OpenAI-compatible Chat Completions and tool calls.
The native model alias uses a 65,536-token context budget and an 8,192-token
output ceiling. These are conservative deployment budgets, not advertised
model limits; omitting them makes this upstream custom-model route resolve
the generation limit to two tokens.
The optional `/models` metadata path is admitted for the same selected provider.
No fixed provider, independent model credential, MCP server, browser or remote
host is configured. TLS uses ABB's ordinary PEM environment trust integration.

`requirement.md` describes testable capabilities and absent external services.
Readiness, enabled state and Case count remain in `resources/registry.toml`.
