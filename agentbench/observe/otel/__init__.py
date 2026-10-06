"""Optional, SDK-independent OpenTelemetry observation.

Span lifecycle/topology and observed model/tool bodies use public gen_ai
semantic attributes. Local abb.* correlation IDs, payload references and
omission diagnostics live in FileExporter metadata and its JSONL projection,
not in the shared provider's public attributes. This avoids passing local
plumbing to SDK privacy filters without deleting any original local evidence
or changing their rules. Unknown attributes from external instrumentation still
reach the SDK and can degrade capture; incomplete spans remain explicit errors.
"""
