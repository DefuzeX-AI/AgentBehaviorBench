# Result storage

Managed runs write execution evidence directly into Agent-owned trajectories.
Suites contain scheduling state and checked references. There is no completion-time
archive conversion, and new writes never unpack an archive.

```text
results/
  suites/<suite-id>/
    plan.json
    events.json                 scheduling journal and result references
    gt.json                     references to Agent-owned GT results
  agents/<agent-id>/
    agent.json
    records/<sha256>.json       immutable results referenced by Suite events
    preparations/<id>/         generation diagnostics and SDK recovery state
    cases/<storage-id>/
      case.json                published prepared Case
      trajectory/<id>/
        run.json               host execution, cleanup and trace acceptance
        manifest.json          SDK execution summary and step index
        case.json              exact SDK-loaded Case with execution identities
        process.json           execution configuration/provenance
        steps/0001/
          input.json           SDK Input contract
          request.json         Agent invocation contract
          result.json          native Agent result
          submission.json      SDK-committed submission and evidence
          otel-status.json     capture validation; other capture metadata stays here
          spans.jsonl          step traces, alongside OTel/live traces when present
          otel-payloads/       ordinary file paths sharing immutable blob bytes
        blobs/<sha256>         content-addressed payload storage
        judge/
          context.json         checked references to Case, Inputs and submissions
          report.json
        judge-task.json        durable host Judge task state
        logs/                  network, SDK, host and controller timing streams
        sdk-repo/              SDK-native repository/ledgers, where required
        judge-state/           SDK-native host Judge recovery state, where required
        recovery/              recovery records, when present
    gt/<suite-id>/             GT calls and evaluations for this Agent
```

SDK-specific private files are retained under their native names. Optional
workspace/replay evidence and diagnostics are retained when produced. Input,
invocation, native output and committed submission are separate contracts: they
must not be collapsed just because some fields coincide.

## Write lifecycle

1. Allocate the Agent Case slot and trajectory, then persist host status.
2. Write each step directly under `steps/<ordinal>` as it runs. Publish JSON
   atomically; append trace streams while execution is active.
3. Name immutable OTel payloads by their redacted content hash. When collecting
   a response, publish a trajectory blob and hard-link step payload paths to it.
   Filesystems without hard links retain ordinary copies. Mutable event streams
   remain separate while the producer is running.
4. Save Judge context as path-and-SHA-256 references to the already committed
   Case, Inputs and submissions. The Judge verifies and expands those references
   in memory. SDK request ledgers remain in place for cancellation and retry.
5. Stop containers and validate host trace evidence. Only then remove temporary
   `channel`, `agent-request` and `agent-output` communication directories.
   Failed cleanup or unaccepted traces retain transport files for diagnosis.
   No execution artifact is moved or repacked at completion.

Running, failed, completed and resumed trajectories use the same paths. A Judge
retry updates its task/report and native ledger without copying the execution
history. Execution, Judge, evidence and cleanup status remain distinct.

Case storage IDs are scoped to a Suite and slot, so equal Case indexes in separate
Suites cannot overwrite each other. Every execution receives a new trajectory.
The published Case and execution Case have different identity/lifecycle roles.
Suite `events.json` remains a JSON array; large outcome fields reference immutable
Agent records by relative path and digest. Source GT is independent of generated
GT evaluations. Default GT evaluation reads saved evidence without rerunning the
Agent.

## Historical compatibility

`observe/artifact_paths.py` accepts both current paths and historical
`evaluation/inputs` paths. `observe/legacy_archive.py` only reads previously
written `abb.trajectory.v1` archives and supports explicit restoration when a
historical execution is resumed. It is not a new-run writer or completion hook.
Historical results are not automatically migrated. Legacy `attempts` references
remain readable; new executions use `trajectory`.
