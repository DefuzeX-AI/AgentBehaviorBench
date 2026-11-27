# Collecting Agent traces

Choose the profile in the registered unit's outer `agent.toml`. Inspect the pinned launcher and its actual runtime first. One Case attempt owns one receiver inside the Agent container. The worker starts it before loading the target and closes it after adapter shutdown. Persistent sessions reuse the receiver across Inputs. A standalone observe run follows the same lifecycle.

### Automatic selection

`agentbench agent add -b` fills `[otel]` when `--otel-profile` is omitted. It reads the dependency declarations in the downloaded source. Nothing is imported or executed.

| Evidence | Selected profile |
| --- | --- |
| A direct dependency on an OTLP trace exporter | `native-otlp` |
| Python graph binding | `langfuse-auto` |
| Python ACP source | `python-auto` |
| `package.json` | `node-auto` |
| `pom.xml` or a Gradle build file | `java-auto` |
| `Cargo.toml`, `go.mod` or a Bun lockfile, with no exporter | `unsupported` |
| No build file at the source root or one level below | `unconfigured` |

A LangGraph binding always counts as Python. For ACP the build file identifies the runtime, since the launcher is usually a Python wrapper. A compiled executable takes precedence over a `package.json` that may only distribute it. `reason` records the file that decided a native selection and any other runtime found in the source.

A declared exporter does not prove that the target starts it. If a real run reports `zero_spans` for a selected `native-otlp`, supply the upstream enable switch in `enable_env` or choose the profile explicitly.

### Native OTLP

For a product that starts its own exporter, point that exporter at the attempt's receiver. Supply upstream enable switches only when the pinned product documents them.

```toml
[otel]
profile = "native-otlp"
protocol = "http/protobuf"
enable_env = { COPILOT_OTEL_ENABLED = "true" }
```

Set `capture_content = false` to disable content in the OpenClaw plugin or Python instrumentor. Other exporters follow their own supported content controls.

The target gets the service name, base endpoint and signal-specific endpoint. The receiver accepts HTTP protobuf, HTTP JSON and gRPC. HTTP accepts gzip and chunked transfer. The configured protocol must match the upstream exporter. [OTLP specification](https://opentelemetry.io/docs/specs/otlp/)

### OpenClaw Gateway

```toml
[otel]
profile = "openclaw"
```

The image installs the matching official diagnostics plugin through OpenClaw's plugin installer. Each Gateway receives the plugin registry and its own diagnostics configuration. The plugin chooses which model, tool and content events to export. The ACP bridge carries the user interaction. OpenSoul uses its own `opensoul` profile for its pinned diagnostic configuration. If its Gateway reports that the diagnostics plugin failed to start, `otel/status.json` records the upstream error independently from the ACP result. [OpenClaw OTel configuration](https://docs.openclaw.ai/gateway/opentelemetry)

### Python LangGraph binding

```toml
[otel]
profile = "langfuse-auto"
```

The worker passes the official Langfuse `CallbackHandler` in the graph's runnable config. Langfuse SDK 5.2.0 uses an isolated OpenTelemetry provider and an HTTP/protobuf exporter pointed at the Case receiver. The local receiver archives the export and writes the redacted span inventory. This setup needs Python 3.11+ and a binding that propagates callbacks. Existing LangGraph units declaring `python-auto` select this profile at build and launch. Python ACP units using `python-auto` launch their command with `opentelemetry-instrument`. [Langfuse LangGraph tutorial](https://langfuse.com/integrations/frameworks/langgraph)

The `node-auto` profile preloads Node instrumentation into the target command using `NODE_OPTIONS`. The `java-auto` profile sets the JVM's `JAVA_TOOL_OPTIONS` to load the checksum-pinned Java agent. Coverage depends on the libraries that execute inside that process. ACP terminal tools started by ABB have their own environment.

### File exporters

Use `profile = "file-export"`, `file = "trace.json"` and `file_format = "otlp-json"` for an upstream OTLP JSON file. The target launcher receives the private output path as `ABB_OTEL_FILE`. Supported special formats are `llxprt-jsonl` for runtime span records and `whip-session` for the Agent CLI's post-session OTLP export. Rows identify the transport so downstream readers can distinguish the two.

### Verification

Open `otel/status.json` in the attempt directory, then inspect `otel/spans.jsonl`. Each JSONL line retains the resource, instrumentation scope, OTLP IDs, original nanosecond timestamps, links, events and exported attributes after the benchmark's redaction rules. Cite the filename and one-based line number.

### Raw exports

Every export is archived exactly as received before any span row is derived from it. `otel/spans.jsonl` is derived from that archive. A row's `archive` names the archived file and its batch number.

| Transport | Archived bytes | File |
| --- | --- | --- |
| HTTP | The request body as sent, before gzip decompression or parsing | `otel/raw/NNNNNN.pb`, `.json` or `.bin`, plus `.gz` for gzip |
| gRPC | The `ExportTraceServiceRequest` message bytes, after gRPC framing and compression | `otel/raw/NNNNNN.pb` |
| File export | The Agent's trace file, byte for byte | `otel/raw/NNNNNN-<original name>` |

`otel/raw/index.jsonl` records one `received` event per archived file: batch number, file, SHA-256, size, transport, content type, content encoding and receive time. A later `accepted` event lists the derived `spans.jsonl` lines. A `rejected` event gives the reason. Rejected and unsupported requests are archived too. A request that exceeds the size limit while it is being read is not archived, because its body was never complete. `status.json` reports `raw_batches` and `raw_redacted: false`.

A protobuf archive can be posted unchanged to any OTLP/HTTP trace endpoint with its recorded content type and encoding. For example, Langfuse accepts it at `/api/public/otel/v1/traces`.

The archive is not redacted. It can contain credentials, prompts and other content the Agent exported. Files are owner-only (`0600`, directory `0700`). Viewers and artifact readers refuse `otel/raw/`, and Judge requests never attach it. Keep it on the machine that ran the attempt. Do not commit it, share it or upload it, except to an observability backend you control.

`span_count` counts persisted Agent-native and auto-instrumented spans. `record_count` includes every received record. `zero_spans` means the configured window closed with zero Agent spans. `unconfigured` and `unsupported` describe profile selection. `incomplete` reports a collection error. Inspect the execution result independently. Per-Input `framework.jsonl` can exist even if the Agent exporter emitted nothing; ABB does not turn those records into OTel spans. A claim about tool output requires an actual result field or event. A claim about message delivery requires independent evidence of delivery.
