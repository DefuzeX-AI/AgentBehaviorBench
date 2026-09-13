# DefuzeX Model Interceptor

This standalone Linux container transparently intercepts model HTTP traffic for
one AgentBench Docker Agent. It owns netfilter and TLS termination; the Agent
container shares its network namespace but cannot access upstream credentials.

Matched OpenAI Chat Completions, OpenAI Responses, and Anthropic Messages
requests retain their source protocol skin while the target plugin rewrites the
upstream URL, model, and authentication for OpenRouter. Streaming responses are
relayed immediately and recorded completely. The legacy `max_trace_bytes`
setting is now an in-memory spool threshold, not a capture limit: larger streams
spill to temporary storage. No request or response body is cut to fit this value.
Storage/resource failures fail visibly instead of claiming a complete trace.

Events retain decoded `payload` and complete `raw_body` text (including SSE
termination and usage events). Requests also retain `source_raw_body` before
protocol/model rewriting. Known credentials are still redacted. Existing truncated
logs cannot be restored; a new run is required to collect missing network data.
Final event serialization still materializes the complete body in memory; this
does not promise unlimited capacity beyond container memory and temporary storage.

The service is configured only through the JSON file mounted at
`/run/secrets/interceptor_config`. It emits machine-readable trace events to
stdout with the `DEFUZEX_TRACE ` prefix.

## Source layout

```text
src/
├── defuzex_model_interceptor/
│   ├── entrypoint.py           # Validate config and launch the proxy
│   ├── config.py               # Configuration values and validation
│   ├── contracts.py            # Adapter interfaces and exchanged data
│   ├── registry.py             # Compose built-ins and load installed plugins
│   ├── proxy/
│   │   ├── addon.py            # mitmproxy request/response lifecycle
│   │   ├── loader.py           # mitmproxy script entry point
│   │   └── netfilter.py        # Linux namespace routing rules
│   ├── routing/policy.py       # Declared model and tool egress matching
│   ├── targets/openrouter.py  # Upstream URL, model and request preparation
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
- `targets/` owns the destination service. OpenRouter receives per-call wire
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
For a new destination service, add an adapter under `targets/`. Reuse shared
auth, JSON and SSE behavior when the protocol actually matches it.

Unknown HTTP egress is denied; non-root TCP is redirected on every port. IPv6
and non-DNS UDP are blocked. Google supports header or query API keys and
rejects ambiguous credentials. `network-isolated` remains restricted to keyless
local protocols inside a private Agent namespace.

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
The target is configurable OpenRouter, not a hard-coded DeepSeek model.
32 original-client cases and separate fault checks are available in
`tests/acceptance/interception`; see `docs/interception/acceptance.md`.
