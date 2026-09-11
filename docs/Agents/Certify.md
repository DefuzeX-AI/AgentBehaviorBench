# Certification

Certification decides whether an adapting Agent is runnable enough to enter the
default batch set.

The default CLI now shares the container-local KUMA core with `run`. It requires
the Agent's evaluation Profile and local SDK source, then checks Case/Input,
Submission/output, OTel/Evidence and Judge identities on the host. Merely changing
the Registry to ready, or passing an observe invocation, is not certification.

## Status Lifecycle

Use this Registry state while integrating:

```toml
enabled = true
status = "adapting"
```

Run:

```powershell
python -m agentbench certify <agent-id>
```

If every requested Case completes without invocation or runtime errors,
AgentBench changes only that Agent's Registry entry:

```toml
status = "ready"
```

## Ready Versus Benchmark Score

`ready` means the adapter works:

- Docker builds and starts.
- The worker receives SDK Inputs.
- For an Agent with required model interception, the Model Interceptor captures
  a complete request/response pair.
- The Agent returns JSON-compatible output.
- Every requested Case completed.
- No `AgentInvocationError` or `DockerSessionError` occurred.

`Judge FAIL` means the adapter ran, but the Agent output did not satisfy the
benchmark. That is benchmark-quality work, not adapter-readiness work.

Examples:

```text
Running Agent inputs and DefuzeX Judge... FAILED | AgentInvocationError
Certification failed. Agent remains adapting.
```

```text
Running Agent inputs and DefuzeX Judge... OK | Judge: issue
Result: FAIL | cases=1/1
Certification completed with benchmark failures. Agent is now ready.
```

```text
Running Agent inputs and DefuzeX Judge... OK | Judge: pass
Result: PASS | cases=1/1
Certification passed. Agent is now ready.
```

## Artifacts

`certify` always writes an atomically updated JSON result under `results/`.

Open it later:

```powershell
python -m agentbench view results\certify-<agent-id>-<timestamp>.json
```

When diagnosing, inspect the first boundary that failed:

| Stage | First files to inspect |
| --- | --- |
| SDK configuration | requirement file, `DEFUZEX_API_KEY`, provider selection |
| Starting Agent | `agent.toml`, Dockerfile, package install, runtime paths |
| Generating Case | requirement content, service response, sensitive-data rejection |
| Running Agent inputs | worker stdout/stderr, input mapping, Model Interceptor Trace, timeout |
| Judge issue with completed Cases | public `output`, requirement criteria, Agent behavior |
| Registry update | target `status` field and concurrent edits |
