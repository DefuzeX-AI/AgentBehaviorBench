# Portable ATIF and recorded trace bundles

This opt-in ABB export preserves recorded evidence without exporting desktop replay
state, accumulated UI snapshots, credentials or an entire runtime directory.
The original collectors, ownership resolver, Agent behavior, Judge/GT contracts
and the legacy `abb.agent-trajectory.v1` contract are unchanged.
Application integration is a separate, approval-gated stage.

## Commands and APIs

Use the existing isolated Python 3.12+ Harbor environment described in
[the ATIF experiment](../experiments/atif/README.md). Harbor remains pinned to
`ec6aeab7fe0eb51df52b4e72c524daf5ea9cc5f4`, producing `ATIF-v1.8`.

```sh
cache/atif/venv/bin/python -m agentbench.experiments.atif export --bundle \
  --input <completed-run> --output <export-parent> --adapter deepagents
cache/atif/venv/bin/python -m agentbench.experiments.atif verify-bundle \
  --input <export-parent>/run-xxxxxxxx
cache/atif/venv/bin/python -m agentbench.experiments.atif run --bundle \
  --config experiments/atif/experiment.toml --case langgraph-two-children \
  --output <new-experiment-directory>
```

`export_bundle(directory, output, adapters=(), allow_incomplete=False,
evidence_files=())` lives in `agentbench.trajectory.atif.bundle`.
`verify_bundle(directory)` lives in `agentbench.trajectory.atif.bundle_validation`.
The latter only reads the supplied bundle and uses a private temporary directory;
it needs neither original paths, a local artifact database, Docker nor a provider.
It raises on corruption/semantic mismatch and otherwise returns measured coverage.
The CLI uses exit 0 for valid exports (including partial runs), 1 for export
failure and 2 for failed portable verification or unmet live acceptance conditions.

`--bundle --output` names a **parent**, unlike the old export command. A complete
package is published into `run-<first-eight-safe-run-ID-characters>`, with `-2`,
`-3`, etc. for collisions. The full run ID remains in the manifest. Publication
uses a private staging directory, an exclusive name reservation and a native
atomic no-replace rename. An unsupported OS primitive fails closed. Failed
exports leave a separate `export-failed-*.json`, never a successful partial package.

## Bundle layout

```text
run-xxxxxxxx/
  trajectory.json
  manifest.json
  runs/
    events.jsonl
    association.json
    model-calls/0001/
      call.json
      record.json
      request.json
      response.json (or .sse/.txt, according to captured content)
      stream-events.jsonl (only when actual llm_delta records exist)
    tool-calls/0001/
      call.json
      record.json
      arguments.json
      result.json (or .txt)
    sources/source-0001/
      records.jsonl
      original-layout.json
    files/
      structured-values.jsonl
      <explicitly declared output files>
```

Paths are conditional: equal values may refer to an earlier file instead of
writing another copy. Sources are enumerated from the existing evidence snapshot;
the manifest records original source paths and observed source labels. There is
no framework/Agent-name dispatch for directory naming. Source IDs and call
numbers are deterministic readable indexes, not chronology or ownership rules.
Native record, run, invocation, session, span and call identities are preserved.

The collector reader defines the base evidence inventory. Callers can declare
additional files (including unknown/binary observations) through `evidence_files`.
The experiment runner adds its configured actual workspace output files. Arbitrary
runtime directories, private keys, caches and other undeclared files are excluded.
Do not add credentials to an evidence inventory. Known process credentials and
private-key PEM material encountered during writing cause failure rather than
silent alteration of the evidence. Existing collector redaction is retained.

## Readable trajectory and portable references

Builder version 4 derives ATIF messages and tool executions from invocation,
ACP and framework evidence. Both assigned and unassigned interceptor calls are
kept in `runs/`. They contribute no steps, wire-only tools, usage or reasoning
to the trajectory. A callback linked to a wire request retains its own input and
output. Unassigned native operations may appear in `extra.abb.unassigned_records`.

Manifest coverage counts all trace operations. A run can therefore have one
observed network model call and a two-step user/agent conversation with no
framework model step. Step details refer to package-relative evidence.
No text equality or filesystem order is used to invent parent/child ownership.

A typical step reference points to `runs/model-calls/0001/call.json`. That file
contains `record_ref`, owner/identity metadata and `body_refs` for the actual
request/response. A source record or shared structured value can include a
one-based `line` in a JSONL file. SHA-256 values occur in the manifest, not as
opaque evidence filenames.

`EvidenceResolver(root, manifest["files"]).resolve(ref)` decodes `json`, `utf8`,
`bytes` and `packed` references, including optional JSONL line indexes. Source
`records.jsonl` contains value envelopes; use `resolver.unpack(json.loads(line))`.
Each envelope has `format`, `value` and a separate `body_refs` array. A body's
`pointer` is an array of original dictionary keys/list indexes, and its `path`,
`encoding` and optional `line` locate the value that replaces the null slot.
Original user keys never act as control markers. Booleans/numbers, nulls, partial
JSON arguments and full strings remain their original types/values.

Large structured values share a readable JSONL pool to avoid filesystem allocation
bloat from thousands of tiny files. The storage threshold affects placement only;
there is no truncation or maximum content size. Identical bodies share storage;
independent calls/events always retain their independent identities. No history
prefix/delta assumption is made across model requests.

Captured wire bodies are written verbatim. Parsed-only data is labeled structured,
never passed off as raw HTTP/SSE. Source JSON bytes are encoded with a serializer
recipe **only after exact byte comparison** with the captured bytes. Noncanonical,
invalid or binary source data stays opaque. The reconstruction is checked against
both original bytes and their recorded hashes. Stream deltas retain the actual
original event with call ID, sequence, timestamp and payload; no unproven byte
range or invented timestamp is used.

## Verification and boundaries

Export freezes source digests, runs the existing reader/resolver/official assembler,
externalizes diagnostics, validates official ATIF, restores every selected source
byte and structured record, checks the source again, and publishes atomically.
`verify_bundle` independently restores an isolated run from the package, invokes
the shared ABB reader/identity resolver and checks the existing conservation,
content and ownership contracts. New reference-mode raw equality uses original
source file/line identity, because copied files have new filesystem mtimes; the
old inline-mode validation remains unchanged. Recorded event timestamps and
source line order are never rewritten.

The manifest inventories every file except itself (self-hashing would be circular),
with size, SHA-256 and media type. It also records source byte hashes, raw record
identity/hashes, operations and ownership, coverage/issues, dependency/converter
provenance and exclusion categories. Hashes establish integrity relative to the
manifest, not an externally signed attestation of collection.

`source_bytes` counts the selected original evidence. `legacy_atif_compact_bytes`
measures the same official document before externalization. Actual package size
includes manifest and all files. `reused_representation_bytes` counts cumulative
avoided writes/representations; it is **not** a claim that source bytes shrank by
that amount. Reports compare source + previous inline ATIF to the complete package
and separately show filesystem allocation and compressed transport size.

Valid ATIF does not imply a successful Agent task or complete telemetry. Failed,
cancelled, missing and unknown evidence remain reported. A model retry is not
performed to make an acceptance report green. Native macOS behavior is exercised;
Windows and Linux branches require separate native execution tests before claiming
support has been verified there.


## Native evidence closure (2026-11-16)

`agentbench.observe.evidence_inventory` owns native payload discovery, guarded
stable reads and native reference validation. Both the host adapter and portable
exporter consume this shared contract. Only ABB OTel envelopes interpret
`abb.*_ref` attributes; ordinary business fields remain opaque. Export and offline
verification reject unresolved native references, even when the listed files and
ATIF document pass all other checks. Incomplete collection cannot be described as
complete merely because the supplied subset can be reconstructed.

Historical host snapshots may call `recover_payloads` with retained native output.
It restores only missing referenced files, requires identical source span
envelopes, checks source stability, and returns recovery provenance. It does not
edit the original run or infer execution identity. A complete snapshot has no
dependency on the original directory. Live readers retry `EvidenceChanged`; path
violations and malformed complete records are not treated as transient errors.

The shared interceptor `observation.http_observer.HTTPObserver` now owns HTTP
capture, with `observation.body.prepare_body` providing bounded decoding before
redaction. Evidence explicitly declares `decoded_redacted` representation.
Forwarded bytes are unchanged. Unsupported encodings, invalid/incomplete streams
and decoded-size limits remain explicit gaps; unknown compression is never saved
as an unsanitized opaque body. Brotli requires the bounded API in version 1.2+.
Limits are supplied by the embedding configuration. These changes do not add
model/span correlation or reclassify historical unknown ownership.
