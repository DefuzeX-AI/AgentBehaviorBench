# Collecting Agent traces

Choose the profile in the registered unit's outer `agent.toml`. Inspect the pinned launcher and its actual runtime first. One Case attempt owns one receiver inside the Agent container. The worker starts it before loading the target and closes it after adapter shutdown. Persistent sessions reuse the receiver across Inputs. A standalone observe run follows the same lifecycle.

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
profile = "python-auto"
```

The LangChain instrumentor loads before the worker imports the target graph. Its provider exports to the Case receiver. For an ACP command that runs a verified Python LangChain Agent, the same profile launches it with `opentelemetry-instrument` before the target imports its libraries. The existing LangGraph callback still records framework events separately. Inspect the installed instrumentation's supported libraries whenever the pinned Agent runtime changes.

The `node-auto` profile preloads Node instrumentation into the target command using `NODE_OPTIONS`. The `java-auto` profile sets the JVM's `JAVA_TOOL_OPTIONS` to load the checksum-pinned Java agent. Coverage depends on the libraries that execute inside that process. ACP terminal tools started by ABB have their own environment.

### File exporters

Use `profile = "file-export"`, `file = "trace.json"` and `file_format = "otlp-json"` for an upstream OTLP JSON file. The target launcher receives the private output path as `ABB_OTEL_FILE`. Supported special formats are `llxprt-jsonl` for runtime span records and `whip-session` for the Agent CLI's post-session OTLP export. Rows identify the transport so downstream readers can distinguish the two.

### Verification

Open `otel/status.json` in the attempt directory, then inspect `otel/spans.jsonl`. Each JSONL line retains the resource, instrumentation scope, OTLP IDs, original nanosecond timestamps, links, events and exported attributes after the benchmark's redaction rules. Cite the filename and one-based line number.

`span_count` counts persisted Agent-native and auto-instrumented spans. `record_count` includes every received record. A span emitted by the `agentbench.observe` scope is recorded as `framework_projection` even when forwarded through OTLP. `zero_spans` means the configured window closed with zero Agent spans. `unconfigured` and `unsupported` describe profile selection. `incomplete` reports a collection error. Inspect the execution result independently. The per-Input SDK files and `framework.jsonl` can exist even if the Agent exporter emitted nothing. A claim about tool output requires an actual result field or event. A claim about message delivery requires independent evidence of delivery.
