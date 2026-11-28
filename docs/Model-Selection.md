# Model selection

Model selection follows the Agent's declared integration constraints, not its framework name.

| Deployment | Selection |
| --- | --- |
| Replacement-mode Agents, including LangGraph | Existing shared run-level model resolver |
| ACP Agents without a provider pin | Same resolver, mapped to the Agent's native configuration |
| MiniMax Code (`minimax-code`), native | Requires `MINIMAX_API_KEY` |
| Claude Agent ACP (`claude-agent-acp`), native | Requires its configured Anthropic Messages endpoint and `CODEX_*` settings |
| Qwen Code (`qwen-code`), native | Requires `DASHSCOPE_API_KEY` and `QWEN_*`; native web search also uses DashScope Responses |

## Shared settings

The bundled catalog and `.env.example` select `ABB_MODEL_PROVIDER=defuze_server`.
Set `KUMA_API_KEY` to use the Defuze model gateway. The default family is `deepseek`
and the actual model is `deepseek-flash`; `DEFUZE_MODEL_FAMILY=minimax` selects the
default `minimax/minimax-m3` model instead. `KUMA_BASE_URL` defaults to
`https://defuzex.ai/api/agentdefuze`. Missing keys and permission failures stop
startup without fallback. Use `--env-file` to select another dotenv file; existing
process environment variables take precedence over dotenv values.

Set `ABB_MODEL_PROVIDER` explicitly to use another service. A custom provider
catalog without `default` retains legacy credential-priority selection.
See the [Defuze target contract](../agentbench/services/model-interceptor/src/defuzex_model_interceptor/defuze_server/README.md)
for permission checks, client settings and supported protocols.

| Provider | Credential | Model | Optional base URL override |
| --- | --- | --- | --- |
| Defuze Server (default) | `KUMA_API_KEY` | `DEFUZE_MODEL` | `KUMA_BASE_URL` |
| OpenRouter | `OPENROUTER_API_KEY` | `OPENROUTER_MODEL` | `OPENROUTER_BASE_URL` |
| DeepSeek (DS) | `DEEPSEEK_API_KEY` | `DEEPSEEK_MODEL` | `DEEPSEEK_BASE_URL` |
| GLM | `GLM_API_KEY` | `GLM_MODEL` | `GLM_API_BASE_URL` |

`[model] provider` in agent.toml pins the provider for that Agent and takes precedence
over `ABB_MODEL_PROVIDER` and the run-level provider object. Otherwise
`ABB_MODEL_PROVIDER` selects the run default. `--model` overrides `ABB_MODEL`,
which overrides the selected provider's model variable. No provider or model is silently
substituted when the selected configuration is incomplete or a request fails.
Tool credentials such as `TAVILY_API_KEY` remain separate. KUMA model-gateway access
and KUMA evaluation are separate operations even when they use the same API key.

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

Shared ACP interception is controlled by one host-side constant:
`ACP_MODEL_MODE` in `agentbench/runtime/interception/policy.py`. Its default is
`"replace"`; change it to `"observe"` and restart the host process to restore
native forwarding. This is not an Agent manifest field or a per-Agent option.
Explicit `model.source="native"` integrations retain observe mode in either case.

The runtime resolves the selected service on the host and passes the model, base
URL and provider ID through internal `ABB_AGENT_MODEL_*` variables. In replace
mode the launcher receives a fresh proxy token in `ABB_AGENT_MODEL_API_KEY`;
only the interceptor receives the real key and replaces outgoing model requests.
In observe mode the launcher receives the selected real key and the proxy records
native requests and responses without substitution. Do not declare these internal
variables in `.env` or runtime input lists. Upstream code and Agent tools remain
unchanged. Run provenance includes the effective mode; switching modes requires a
new run instead of resuming results collected under the other policy.

Defuze uses separate source and target settings: ACP defaults to the native
`deepseek` client with `deepseek-chat` at `https://api.deepseek.com`, while the
interceptor forwards to the Defuze gateway with the actual selected model.
`DEFUZE_CLIENT_PROVIDER`, `DEFUZE_CLIENT_MODEL` and `DEFUZE_CLIENT_BASE_URL` can
select another supported client profile. Both configurations are recorded in
provenance. Native catalogs and explicit provider pins remain authoritative;
this does not make every ACP launcher compatible automatically. Separate-target
observe mode and `/models` metadata forwarding are currently rejected.

The runtime derives the exact HTTPS host, port and `/chat/completions` path from the
selected base URL. It does not admit all provider hosts or wildcard paths. Hermes also
opts into `GET <base>/models`; replacement mode authenticates this exact catalog
endpoint with the selected service key. Its other tool routes remain separate.

Current shared ACP profiles support one OpenAI-compatible Chat Completions model.
Custom provider headers, nonstandard endpoint suffixes and multi-target routing are
rejected explicitly for shared ACP profiles; generic replacement integrations
retain their richer routing options.

Cline selects its native OpenRouter, DeepSeek or ZhipuAI provider and validates model IDs
against the catalog bundled with CLI 3.0.62 / `@cline/llms` 0.0.83. Unknown IDs fail instead
of silently becoming the provider default. The catalog snapshot is in
`resources/agents/08-cline/bootstrap/model-catalog.json`; refresh it when upgrading the
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
