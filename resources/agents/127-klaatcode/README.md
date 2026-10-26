# Klaat Code native ACP integration

Pinned upstream: https://github.com/KlaatAI/klaatcode at
`b988be7cf6ffe7878e87ed3e720759e0f7247c33` (package.json version 2.5.0).
ABB restores the Git source into ignored `agent/`. Bun installs its frozen
lockfile and runs the unit-local TypeScript ACP startup wrapper; upstream bytes are
unchanged. The native class, transport, tools, permissions and session loop run
inside the container as UID 10001.

The native ACP CLI constructs a KlaatAIClient but does not wire the TUI's
custom-model selector. `bootstrap/acp.ts` wraps only initialize registration and
calls the client's existing public `setCustomEndpoint` method after native
initialization. Access to its TypeScript-private `client` property is explicitly
revision-dependent. Other requests, streamed text, tool results, errors and
permission decisions pass through the native implementation unchanged.

The launcher creates a separate 0700 HOME and 0600 native preferences file for
each invocation. Only telemetry is disabled. No model credential is written to
config or argv. A noncredential KLAATAI_API_KEY marker satisfies the native
presence check without asserting Klaatu login. Actual chat authentication uses
ABB_AGENT_MODEL_API_KEY through the native custom endpoint; Klaatu server APIs
are not provisioned or allowed by the network policy. Shared model selection
remains provider-neutral. See requirement.md for deployed limitations.

The native custom endpoint appends `/v1/chat/completions` unless its base already
ends in `/v<digits>`. ABB authorizes the exact selected base + `/chat/completions`,
so use a versioned base (for DeepSeek: `DEEPSEEK_BASE_URL=https://api.deepseek.com/v1`).
The launcher rejects incompatible bases before any prompt rather than changing
routes silently. OpenRouter's `/api/v1` and other compatible versioned prefixes
remain selectable. Proxy settings and model interception are not changed.

Registration remains disabled/adapting until maintainer review. Integration
acceptance, official evaluation and GT findings are separate results.
