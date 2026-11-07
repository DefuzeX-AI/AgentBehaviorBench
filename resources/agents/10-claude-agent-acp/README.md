# Claude Code ACP deployment

This unit packages the pinned
[`agentclientprotocol/claude-agent-acp`](https://github.com/agentclientprotocol/claude-agent-acp)
bridge and its locked Claude Agent SDK dependency. ABB invokes the bridge over
ACP stdio and keeps each Case in a separate empty workspace.

The acceptance profile intentionally reuses a Codex provider that exposes an
Anthropic Messages compatibility route. Supply these variables only at runtime:

- `CODEX_API_BASE_URL`: the Codex OpenAI-style base URL ending in `/v1`.
- `CODEX_MODEL`: the exact provider model ID, such as `gpt-5.5`.
- `CODEX_API_KEY`: the Bearer credential. It is never written into this unit.

When the Codex endpoint uses private DNS and Docker does not inherit the host's
VPN resolvers (for example, Colima configured with public DNS), set
`ABB_DOCKER_DNS` to a comma-separated list of resolver IP addresses. ABB applies
them to the model interceptor's network namespace; the Agent remains behind the
same interception and evidence path.

`bootstrap/launch.py` removes the terminal `/v1` before setting
`ANTHROPIC_BASE_URL`, because Claude's SDK appends `/v1/messages`. The resulting
request still uses the exact Codex endpoint route. The launcher maps the secret to
`ANTHROPIC_AUTH_TOKEN`, disables native API-key auth, and pins the requested model.

The current network manifest admits the tested `z.duxiaoman-int.com` compatibility
route only. A different Codex provider needs an explicit reviewed route update;
changing environment variables alone does not broaden container egress.

`bootstrap/patch_source.py` applies one checked build-time compatibility change
without editing the imported source snapshot: the bridge waits for its optional
session-title request at turn end. Upstream runs that request in the background,
but ABB's one-shot worker otherwise closes the ACP process immediately after the
answer and interrupts that already-started model stream.
