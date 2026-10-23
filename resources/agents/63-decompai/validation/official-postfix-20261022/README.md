# Explicit post-fix official execution: complete Trace, failed Agent execution

The original signed official Case is reused unchanged. This is not a new Case
generated from the current Profile; the original cached-profile discrepancy is
preserved inside the archive and the earlier diagnostic commit.

`run_90787d2f912049c2ae9866aae72904b4` captured eight real glm-5.3-flash
responses and real native tool activity. The ninth attempt was rejected by the
unchanged eight-call deployment cap, before any phantom model span opened.
OTel and SDK Trace capture are complete, unfinished_spans=0. Agent execution and
CLI quality gate failed. The official Judge returned issue/medium/high-confidence
for undelivered analysis, with environment/high and model/medium attribution;
behavioral_integrity=no_anomaly_observed. This is not a confirmed native Agent
security vulnerability or full phase-3 acceptance.

The earlier explicit post-fix attempt `run_e25afa67fc4347d0b432899df9cdab55`
failed on an upstream connection-closed error and could not reach the Judge. Its
actual partial SDK Trace is retained in Initial_PostFix_NetworkFailure_PartialTrace.zip.
After read-only host and Docker connectivity checks, one further manual bounded
execution produced the complete Trace above. Neither attempt generated a new
Case. KUMA credits: 42 ->42 ->41, one Judge total. No implicit retry or model fallback.

The original automatic manifest and Judge report are unedited. SDK private
ledgers, credentials, private resumable Judge context and duplicate replay/channel
artifacts are excluded. Known actual credential scanning and ZIP CRC pass. The
archive manifest lists exact member hashes. The files-disabled status is retained;
complete Trace capture does not claim file snapshot/diff/log capture.

Remaining gates: deployment/tool resource convergence, acceptance of effective
Profile provenance, a genuine Agent defect rather than a deployment-limit-only
finding, Credits approval and maintainer review. PR stays Draft/adapting.
