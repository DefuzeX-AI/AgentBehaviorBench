# Result storage

New managed runs use Agent-owned artifacts. A Suite is the scheduling and
reference journal, not the container for execution evidence.

```text
results/
  suites/<suite-id>/
    plan.json
    events.json                 ordered scheduling events and checked references
    gt.json                     references to Agent-owned GT results
  agents/<agent-id>/
    agent.json
    records/<sha256>.json       immutable result records referenced by Suite events
    preparations/<id>/         SDK generation diagnostics and recovery state
    cases/<storage-id>/
      case.json
      trajectory/<id>/
        manifest.json          metadata, original identities, checked artifact map
        steps/<ordinal>/       invocation, output, submission and original traces
          capture.json         capture, context and redaction metadata
        blobs/<sha256>         shared trace payload bytes
        judge/                 task, referenced context, report
        logs/                  network and timing evidence
        sdk-state/             SDK-native ledgers needed for recovery
        replay/                optional workspace history
    gt/<suite-id>/              GT calls and evaluations for this Agent
```

Case storage IDs are assigned before generation and scoped to a Suite and slot.
The SDK Case ID is recorded in the Case itself. Identical slot numbers from
different Suites cannot overwrite one another. Every execution receives a new
trajectory directory; historical executions are retained.

During execution, the trajectory holds the existing SDK runtime layout, including
the controller/Agent mailbox. Once judging is complete and host cleanup and trace
validation succeed, ABB publishes a compact archive. Incomplete runs retain their
original files for diagnosis and recovery. The archive manifest is published
before source copies are retired; each retained logical file is checked against
its original byte digest.

The terminal archive removes consumed channel copies, stores repeated payloads
once, groups metadata, combines timing streams with byte-range references, and
references Case and submission data when reconstructing Judge context. Execution,
Judge, evidence and cleanup status remain distinct. Agent output and SDK
submission remain separate records. Live and framework traces are retained when
they carry different evidence; they are not discarded merely because they concern
the same model call.

The result reader resolves archived logical paths without creating files. Existing
Suite and trajectory layouts remain readable. An explicit later write restores
the original SDK layout first, preserving byte identities and request ledgers.
Default GT evaluation uses saved evidence and does not execute the Agent again.

Suite event files remain JSON arrays for compatibility with existing CLI readers;
`events.json` is the durable journal. Large outcome fields reference immutable
Agent records by relative path and digest. GT evaluations are partitioned by Agent,
with the Suite retaining only a reference index. Source GT under Agent resources
is independent of these generated results.

No historical results are automatically moved or rewritten. New writes use
`trajectory`; legacy `attempts` GT references remain supported.
