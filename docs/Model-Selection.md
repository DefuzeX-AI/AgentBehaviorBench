# Model selection

Model selection follows the Agent's declared integration constraints, not its framework name.

| Deployment | Selection |
| --- | --- |
| Replacement-mode Agents, including LangGraph | Existing shared run-level model resolver |
| ACP Agents 15-32 and 36, no provider pin | Same resolver, mapped to the Agent's native configuration |
| MiniMax Code (12), native | Requires `MINIMAX_API_KEY` |
| Claude Agent ACP (13), native | Requires its configured Anthropic Messages endpoint and `CODEX_*` settings |
| Qwen Code (14), native | Requires `DASHSCOPE_API_KEY` and `QWEN_*`; native web search also uses DashScope Responses |

## Shared settings

Without an explicit provider, ABB selects the first nonempty credential in this order:
**OpenRouter -> DeepSeek -> GLM**. Configure that provider's key and model:

| Provider | Credential | Model | Optional base URL override |
| --- | --- | --- | --- |
| OpenRouter | `OPENROUTER_API_KEY` | `OPENROUTER_MODEL` | `OPENROUTER_BASE_URL` |
| DeepSeek (DS) | `DEEPSEEK_API_KEY` | `DEEPSEEK_MODEL` | `DEEPSEEK_BASE_URL` |
| GLM | `GLM_API_KEY` | `GLM_MODEL` | `GLM_API_BASE_URL` |

`[model] provider` in agent.toml pins the provider for that Agent and takes precedence
over `ABB_MODEL_PROVIDER` and the run-level provider object. Otherwise
`ABB_MODEL_PROVIDER` selects the run default. `--model` overrides `ABB_MODEL`,
which overrides the selected provider's model variable. No provider or model is silently
substituted when the selected configuration is incomplete or a request fails.
DeepSeek is supported but never mandatory for these deployments. Tool and SDK credentials,
such as `TAVILY_API_KEY` and `KUMA_API_KEY`, remain separate.

For example, to select DeepSeek despite a configured OpenRouter key:

```dotenv
ABB_MODEL_PROVIDER=deepseek
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-flash
```

Use a model available to your account that supports the Agent's required capabilities.

## Native mapping and limits

Ordinary Agents omit `[model]` entirely and inherit default selection. To fix a
provider for one Agent (ACP or replacement-mode LangGraph), add only:

```toml
[model]
provider = "deepseek"
```

Even when an OpenRouter key or global provider override exists, this Agent uses
DeepSeek. Missing `DEEPSEEK_API_KEY` or model configuration fails; it never falls
back to OpenRouter. This pins the provider, while the model ID retains the model
precedence described above. A provider pin cannot be combined with a multi-target
routing file. These settings do not modify SDK/judge model selection.

Hermes has `[model] metadata_paths = ["/models"]` solely to permit its model-list
request. Without `provider`, it still inherits default selection.

The runtime resolves the selected service on the host and passes only its credential,
model, base URL and provider ID to the launcher using internal `ABB_AGENT_MODEL_*`
variables. Do not fill or declare those variables in `.env` or runtime input lists.
The launcher maps them to the upstream Agent's supported configuration. Upstream code
and Agent tools remain unchanged. ACP remains in **observe mode**: the proxy records
native model calls without substituting the provider or credential.

The runtime derives the exact HTTPS host, port and `/chat/completions` path from the
selected base URL. It does not admit all provider hosts or wildcard paths. Hermes also
opts into `GET <base>/models`; its other tool routes remain separate.

Current shared ACP profiles support one OpenAI-compatible Chat Completions model.
Custom provider headers, nonstandard endpoint suffixes and multi-target routing are
rejected explicitly; those richer routing options remain available in replacement mode.

Cline selects its native OpenRouter, DeepSeek or ZhipuAI provider and validates model IDs
against the catalog bundled with CLI 3.0.62 / `@cline/llms` 0.0.83. Unknown IDs fail instead
of silently becoming the provider default. The catalog snapshot is in
`resources/agents/15-cline/bootstrap/model-catalog.json`; refresh it when upgrading the
pinned distribution. Pi's provider-specific thinking options follow the selected service.

For an integration that requires a provider, protocol or provider-owned tool service,
keep its dedicated credential declarations and document the restriction:

```toml
[model]
provider = "minimax"
source = "native"
reason = "Native MiniMax integration requires MiniMax credentials."
```

`source="native"` describes a dedicated integration whose existing routes, protocol
and credentials implement the declared provider; it requires a provider pin. It is
used by MiniMax (`minimax`), Claude ACP (`codex`) and Qwen Code (`dashscope`). Global
provider/model settings do not rewrite these integrations. Changing their provider
requires adapting their native credentials, routes and launcher together.

New onboarding must omit redundant default declarations and repeated setup comments.
It must verify an outer launcher consuming `ABB_AGENT_MODEL_*` for configurable ACP
Agents; if missing, report the integration work needed before generating a complete
configuration. Declare exceptions only when supported by upstream evidence. Do not
infer restrictions from vendor names or disable tools to fit another provider.

## Recovery and verification

Suite provenance records the effective shared provider, URL and model without keys.
Changing an unused provider's settings or rotating the selected key does not invalidate
an Agent's provenance. Changing the effective provider, endpoint or model requires a
linked new Suite; SDK/judge configuration is checked separately as before.

Configuration and offline regression tests do not certify every Agent/provider/model
combination. Earlier provider-specific acceptance records remain historical; a fresh live
Case is required to demonstrate native requests and tool behavior for a new combination.

### Runtime-configurable native clients

A provider-constrained native ACP client that accepts a configurable OpenAI Chat
Completions endpoint, model ID and credential can explicitly opt into runtime
selection while retaining its native declaration:

```toml
[model]
provider = "deepseek"
source = "native"
reason = "The native client supports only this provider's model catalog."
runtime_configurable = true
```

This capability requires a native ACP declaration, an explicit provider and a
nonempty reason. It uses the same provider pin and `--model` precedence as shared
selection. The runtime supplies `ABB_AGENT_MODEL_*` to the launcher and derives the
exact observed Chat Completions route. Static model credentials, routes and
interception environment overrides cannot be combined with this capability;
runtime-owned variables cannot be declared as inputs. The launcher must preserve
and validate the selected model and map the credential/base URL into supported
native configuration. Missing provider credentials fail without fallback.

The capability does not enable Responses, Messages, custom headers, nonstandard
endpoint suffixes or multi-target routing. Such clients retain their existing
native configuration contract. Existing native declarations without this opt-in
continue using dedicated settings and do not consume global model overrides.
Provenance retains `model_source=native`, records the capability and the actual
selected target, and excludes credentials. Whale uses this capability with an
explicit `--model deepseek-v4-pro`; its unsupported Flash alias fails instead of
silently selecting another model.
