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
