# DotCraft native ACP integration

This unit builds the pinned .NET 10 DotCraft application and runs its own
`dotcraft acp` command. The native bridge starts the native AppServer and uses
DotCraft's session engine, tools and permission handling. Source files are not
modified; ignored `agent/` is restored from the pinned Git revision before build.

## Configuration and execution

Follow the repository setup instructions and provide Docker plus a supported
model credential in a private environment file. The runtime chooses provider,
model, endpoint and credential using normal ABB precedence. The launcher writes
native global configuration with the selected target and an environment reference
for the key, runs `dotcraft setup --provider-mode skip` for a fresh workspace,
and starts native ACP. It changes no native tools or permission rules.

OpenAI Chat Completions is an explicitly supported native protocol. No provider
is pinned and no model is renamed. Desktop OAuth and Responses are not required
for this configured deployment. Native optional web search may select a
provider-owned search endpoint; that service is not provisioned by the shared
Chat Completions route and may be denied. The native tool remains unchanged.

The .NET SDK is needed only during image construction. The self-contained
application runs in Linux alongside Node.js, Python, Git, ripgrep and Bash.
Desktop, Satellite, chat-channel packages and external services are not part of
this headless deployment. `requirement.md` defines the evaluation boundary.

To evaluate a bounded Case, create a temporary registry below `resources/` with
schema `defuzex-bench.registry.v1` and an enabled copy of this Agent's entry, then
use `agentbench evaluate dotcraft --registry <temporary-registry> --sdk native`
or `--sdk kuma` with the private environment file and explicit run limits. Keep
the tracked registry disabled/adapting until the project's acceptance workflow
completes. No secret or generated workspace configuration belongs in this unit.
