# DefuzeX Model Interceptor

This standalone Linux container handles model HTTP traffic for one AgentBench
Docker Agent. It owns netfilter and TLS termination; the Agent shares its network
namespace. Adapter registration selects the behavior without a user mode switch:

- **ACP / observe:** preserve native URL, model, credentials, payload and response.
  The Agent receives its declared native credentials. The service needs no
  replacement provider or secret. Token counting also stays native.
- **LangGraph / replace:** retain existing protocol recognition and credential
  substitution. The target plugin selects the configured provider URL, model and upstream
  key; the Agent receives an isolated temporary key.

Both paths enforce explicit egress policy and redact recorded evidence. Observe
requires a declared model or tool destination; recognizing a familiar model API
path alone does not authorize arbitrary hosts. Native HTTP failures and SSE error
frames remain unchanged. Connection failures stay connection failures. Recording
failures reject evidence without replacing the native response. SDK Case generation
and Judge configuration remain separate from the Agent's network behavior.

Streaming responses are relayed immediately and recorded completely. The legacy
`max_trace_bytes` setting is an in-memory spool threshold, not a capture limit:
larger streams spill to temporary storage. Storage failures fail visibly.

Replacement-mode SSE parsing allows up to 16 MiB per event by default, including
the Gemini compatibility stream adapter. This is a per-event framing limit, not
a total response or trace limit. Oversized events fail explicitly; they are not
silently truncated. Larger events may require more memory per concurrent stream.

Events retain decoded `payload` and complete `raw_body` text (including SSE
termination and usage events). Replacement requests also retain `source_raw_body` before
protocol/model rewriting. Known credentials are still redacted. Existing truncated
logs cannot be restored; a new run is required to collect missing network data.
Final event serialization still materializes the complete body in memory; this
does not promise unlimited capacity beyond container memory and temporary storage.

The service is configured only through the JSON file mounted at
`/run/secrets/interceptor_config`. It emits machine-readable trace events to
stdout with the `DEFUZEX_TRACE ` prefix.

## Replacement providers

The host [provider catalog](../../runtime/interception/model-providers.toml) declares
provider priority, credential/model/base-URL environment variable names, default
URLs, optional headers and endpoint paths. Defaults check **OpenRouter → DeepSeek
→ GLM**, selecting the first non-empty API key. Whitespace-only keys are absent.
`ABB_MODEL_PROVIDER` (or an explicit provider name in the host API) overrides this
selection. This checks configuration presence, not remote key validity: request
failures do not silently retry against another provider.

| Provider | API key | Model | Base URL override |
| --- | --- | --- | --- |
| OpenRouter | `OPENROUTER_API_KEY` | `OPENROUTER_MODEL` | `OPENROUTER_BASE_URL` |
| DeepSeek | `DEEPSEEK_API_KEY` | `DEEPSEEK_MODEL` | `DEEPSEEK_BASE_URL` |
| GLM | `GLM_API_KEY` | `GLM_MODEL` | `GLM_API_BASE_URL` |
| Zhipu (explicit only) | `GLM_API_KEY` | `GLM_MODEL` | `ZHIPU_API_BASE_URL` |

Models have no new built-in defaults. `--model` overrides `ABB_MODEL`, which
otherwise overrides the selected provider's model variable. An available key with
missing model configuration fails startup instead of falling through to a different
provider. With no key, the first configured provider is used for normal startup
validation, which reports the missing model or credential.

Copy the catalog and set `ABB_MODEL_PROVIDERS_CONFIG=/absolute/path/providers.toml`
to replace its declarations. Change `priority`, add providers, or change the
credential/model variable names, URLs and endpoint mappings there; no provider
selection branches in Python are needed. Files contain environment variable names,
not credentials. The selected real key is mounted only into the interceptor;
Agents still receive isolated per-run tokens.

DeepSeek defaults to `https://api.deepseek.com`, with Chat Completions, Responses
and Anthropic Messages endpoint mappings. GLM defaults to the standard
`https://open.bigmodel.cn/api/paas/v4` Chat Completions endpoint. The existing
`GLM_API_BASE_URL` setting takes precedence (including a Coding Plan deployment).
`zhipu` uses the same key and model as GLM but the `https://open.bigmodel.cn/api`
base, mapping Chat Completions to `/paas/v4/chat/completions` and Anthropic Messages to
Zhipu's Anthropic-compatible `/anthropic/v1/messages`. It is not in `priority`; select it
with `ABB_MODEL_PROVIDER=zhipu` for Agents whose routes use `anthropic-messages`.
Gemini/Ollama text bridges use the target's Chat Completions endpoint. Protocols
absent from a target's `endpoint_paths` table fail before forwarding; this does not
add cross-protocol conversion for GLM Responses or Anthropic Messages. Change the
catalog only to match the capabilities of the actual deployment.

Endpoint references: [DeepSeek Chat](https://api-docs.deepseek.com/api/create-chat-completion/),
[DeepSeek Responses](https://api-docs.deepseek.com/guides/responses_api/),
[DeepSeek Anthropic](https://api-docs.deepseek.com/guides/anthropic_api/),
[GLM API example](https://docs.bigmodel.cn/cn/best-practice/case/ai-search-engine),
[Zhipu Anthropic-compatible API](https://docs.bigmodel.cn/cn/guide/develop/claude/introduction).

This selection applies to replacement-mode Agent model calls. ACP observe mode
retains native provider credentials. The onboarding builder (`agent add -b`)
continues to use its separate OpenRouter configuration.

## Source layout

```text
src/
├── defuzex_model_interceptor/
│   ├── entrypoint.py           # Validate config and launch the proxy
│   ├── config.py               # Configuration values and validation
│   ├── contracts.py            # Adapter interfaces and exchanged data
│   ├── registry.py             # Compose built-ins and load installed plugins
│   ├── proxy/
│   │   ├── addon.py            # Select the adapter-owned behavior
│   │   ├── common.py           # Shared fields, redaction and local errors
│   │   ├── loader.py           # mitmproxy script entry point
│   │   └── netfilter.py        # Linux namespace routing rules
│   ├── observe/handler.py      # Native forwarding and evidence capture
│   ├── replace/handler.py      # Provider/auth/protocol replacement
│   ├── routing/automatic.py    # Adapter-owned model request recognition
│   ├── routing/policy.py       # Explicit route and tool egress matching
│   ├── targets/compatible_json.py # Shared configured JSON target preparation
│   ├── targets/openrouter.py  # Compatibility target name
│   ├── security/
│   │   ├── auth.py             # Shared bearer and isolated-network auth
│   │   └── redaction.py        # Credential sanitization
│   ├── transport/
│   │   ├── json.py             # JSON parsing and serialization
│   │   ├── sse.py              # Provider-independent stream framing
│   │   └── grpc.py             # HTTP-equivalent to gRPC status mapping
│   ├── observation/
│   │   ├── events.py           # Event output and failure sanitization
│   │   ├── decoders.py         # Payload decoding for trace evidence
│   │   └── capture.py          # Complete response capture and spooling
│   └── error/failure.py        # Error codes, data and shared exceptions
└── model/
    ├── native.py              # Native JSON protocols and streams
    ├── ollama.py              # Ollama chat/generate conversion
    ├── anthropic/auth.py      # Anthropic API key handling
    └── google/
        ├── auth.py            # Google header/query credentials
        ├── gemini.py          # Gemini text and stream conversion
        └── grpc.py            # Google protobuf messages and gRPC envelopes
```

## Dependency rules

- `registry.py` owns built-in adapter selection. The proxy calls the selected
  adapters; adding a provider does not require provider-specific branches in
  `proxy/addon.py`.
- `model/` contains source API semantics, not a file for each model version.
  Adapters can use shared contracts, errors, security and transport helpers.
  They must not import proxy orchestration, the registry, targets or observation.
- `targets/` owns the destination service. The shared JSON target receives per-call wire
  factories from the registry; it does not discover adapters itself.
- `transport/` is provider-independent. Google protobuf imports belong in
  `model/google/grpc.py`; generic status mapping belongs in `transport/grpc.py`.
- Error data depends only on the standard library. `observation/events.py`
  sanitizes error fields before output. Package `__init__.py` files only
  document the package or export public names.

## Extension points and preserved behavior

Third-party model strategy factories register under
`defuzex.model_interceptor.wires`. Each request gets a new strategy instance,
so stream state is never shared. `defuzex.model_interceptor.protocols` plugins
decode trace payloads; they do not perform model conversion. Authentication and
target plugins use the existing `.auth` and `.targets` entry-point groups.
These plugins may export an instance, a class, or a zero-argument factory.
Strategies advertising `grpc=True` implement `encode_response(payload)` for
their own unary protobuf envelope; the proxy does not import Google codecs.

For a new source API, put its conversion and any provider-specific credentials
under `model/`, then register its wire factory and authentication implementation.
For a compatible destination service, add a provider declaration to the host
catalog. Add an adapter under `targets/` only when destination semantics differ.
Reuse shared auth, JSON and SSE behavior when the protocol actually matches it.

Model requests no longer require a per-Agent `llm_interception.routes` entry.
An explicit route still takes precedence for custom endpoints. Otherwise the
proxy matches the `SourceSignature` published by each registered wire factory,
then authenticates against the configured per-run credentials. Signatures live
beside the adapter and specify method, content type, paths and authentication
plugin. More specific paths win; equally specific matches fail as ambiguous.
Provider-compatible custom hosts work without duplicating model URL rules in
every Agent manifest. Recognition does not grant a credential or forward traffic
directly: every recognized call still uses authentication, conversion, the
configured target and the complete request/response trace pipeline.

`routes` may be omitted or empty in both Agent TOML and service JSON. Credentials
are still required; a recognized protocol with missing/invalid credentials fails
authentication and cannot fall through to a tool allowance. Third-party wire
factories can publish a `signature` using the same contract; factories without
one continue to work through explicit routes. No Agent-specific exceptions are
used. Automatic routes live on the individual flow, never in shared config.

Unknown HTTP egress is denied; non-root TCP is redirected on every port. IPv6
and non-DNS UDP are blocked. Google supports header or query API keys and
rejects ambiguous credentials. `network-isolated` remains restricted to keyless
local protocols inside a private Agent namespace.

Non-model HTTP access is allowlisted through `llm_interception.tool_routes`
in the Agent manifest. Rules match the host, port, method and path (excluding
the query string); matching requests retain their destination and produce
`tool_request` / `tool_response` events. Declared model hosts cannot bypass
model interception through a tool rule. When adapting an Agent, declare only
the external endpoints it needs instead of allowing an entire service.

The KUMA evaluation build overlay reads `agentbench/sdk/plugin/kuma/whitelist.json`
to add its backend routes and one release
metadata route: `GET api.github.com:443/repos/DefuzeX-AI/KUMA-DefuzeX/releases/latest`,
with purpose `evaluation`. This permits the SDK's background update check
without disabling it or allowing other GitHub endpoints. These extra routes
apply only to the staged evaluation manifest; the original Agent is unchanged.

Each whitelist entry contains a full `url` and explicit `methods`, for example
`{"url": "https://service.example/api/status", "methods": ["GET"]}`.
Paths match exactly unless they end in `/*`; query strings are not matched.
When integrating another SDK, keep its whitelist JSON in its own SDK directory
and reuse `agentbench.sdk.common.whitelist.whitelist_toml` in its build overlay.
Declare the JSON as package data so installed ABB builds can read it too.

Authentication and target mutations are staged on a request copy. Failed
preparation cannot forward a real key to the original provider. Empty
intermediate stream output must not terminate HTTP/1 chunked responses, and
failed streams must not receive success trailers.

The package layout replaces the old root-level `auth`, `addon`, `events`,
`policy`, `protocols`, `targets` and `wire` modules. Python imports must use the
paths above; protocol IDs, configuration keys, event names and CLI entry points
remain unchanged. Reinstall the service after updating plugin metadata.

Gemini and Ollama bridges currently support text, not tools, images, audio,
cached content or provider-specific controls. Unsupported fields fail closed.
The replacement target and model are selected from deployment configuration.
32 original-client cases and separate fault checks are available in
`tests/acceptance/interception`; see `docs/interception/acceptance.md`.

## Agent-owned network extensions

An Agent can opt in with `network_config = "network/rules.toml"` under
`[llm_interception]`. The path must resolve inside its outer unit (including
symlink resolution). The versioned file supplies `tool_routes` and `token_counting`;
existing inline routes, including evaluation SDK routes, are preserved. There is
no automatic import of executable code from an Agent checkout.

```toml
schema_version = "abb.network.v1"
[token_counting]
mode = "local_estimate"
[token_counting.models]
"openai/gpt-4.1-mini" = "o200k_base"

[[tool_routes]]
host_patterns = ["native-service.example"]
ports = [443]
methods = ["POST"]
path_patterns = ["/review"]
purpose = "content_safety"
required = true
```

The host mounts normalized configuration to the existing service. Ensure the Agent
Dockerfile copies the referenced configuration into the worker as well. No changes
to imported source or ACP session code are needed. New native URLs are configuration;
new counting wire formats belong in `token_counting/protocols/`; counting algorithms
belong in `token_counting/counters.py`. Existing route matching/authentication is the
dispatcher, so no second routing registry or Agent-name conditionals are introduced.

Counting endpoints authenticate the per-run credential before any local response.
`local_estimate` uses an explicit mapping for the actual model selected by BBA, not
the original source model alias. The deterministic `structured-json-bpe-v1` algorithm
encodes the input envelope (including system text, tools, tool results and message
structure). It is approximate, not provider prompt rendering or an upper bound.
Model usage and billing remain untouched. The bundled tokenizers are loaded at
image build time. Unsupported models, media or server-held context return 404;
invalid requests return 400; oversized inputs return 413. Native fallback remains
visible, not disguised as a zero count. Without opt-in, auxiliary requests retain
the real upstream response/status, including unsupported endpoint responses.

`model_auxiliary_request/response/error` do not satisfy a generation checkpoint.
The host drains them before acceptance. Responses record origin, algorithm version,
target/source models, encoding and request digest. Ordinary model evidence and
unknown-request/authentication failures keep their existing strict policy.

Tool purposes `metadata` and `content_safety` supplement `tool` and `evaluation`.
Requests and full responses remain observable. Optional metadata HTTP failures do
not invalidate model capture. `required=true` requires every observed operation to
have a successful HTTP response; failure is reported separately from capture loss.
A successful HTTP response containing a native rejection is preserved, not changed
to an allow verdict. The native Agent determines how that decision affects its task.
A failed required operation remains a failed acceptance even if a later retry works.

Offline service regression command (built image already contains the dependencies):

```bash
docker build -t abb-interceptor-test agentbench/services/model-interceptor
docker run --rm --network=none --entrypoint python \
  -v "$PWD/agentbench/services/model-interceptor/tests:/tests:ro" -w /tests \
  abb-interceptor-test -m unittest discover -v
```
