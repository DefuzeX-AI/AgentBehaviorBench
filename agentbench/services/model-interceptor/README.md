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

## Boundaries and extension points

- `policy.py`: declared model routes and explicit tool exceptions. Unknown HTTP
  egress is denied; non-root TCP is redirected on every port. IPv6 and non-DNS
  UDP are blocked, not translated. Do not publish the private proxy externally.
- `auth.py`: temporary-token validation. Google supports header or query API
  keys (ambiguous credentials are rejected). `network-isolated` is only for
  keyless local protocols in a private Agent namespace.
- `targets.py`: target provider and model selection. Authentication and route
  mutations are staged on a request copy; plugin failures cannot forward a real
  key to the source provider.
- `wire/`: per-call Strategy factories selected by protocol ID. Third-party
  factories register under `defuzex.model_interceptor.wires`. The existing
  `protocols` entry points remain observation decoders, not converters.
- `gemini.py`: text semantic mapping; `wire/grpc.py`: bounded protobuf frames,
  gzip and Google v1beta messages. There is no Google SDK patch in the Agent.
- `addon.py`: lifecycle orchestration, status mapping, streaming capture and
  trace events. Empty intermediate output suppresses HTTP data; it must not
  create an HTTP/1 terminating chunk. Failed streams never get success trailers.

Gemini and Ollama bridges currently support text, not tools, images, audio,
cached content or provider-specific controls. Unsupported fields fail closed.
The target is configurable OpenRouter, not a hard-coded DeepSeek model.
32 original-client cases and separate fault checks are available in
`tests/acceptance/interception`; see `docs/interception/acceptance.md`.
