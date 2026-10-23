# mini-opencode integration acceptance (#522)

This is a phase-one integration smoke test, run on 2026-10-23. It is not a GT
candidate or an official KUMA behavioral evaluation.

## Result and original records

ABB `318cab5b37410fd71c457eb9e5aff11630619b27` runs upstream mini-opencode
`d09f3e96eca1ac3fb40f7e9ab3740ef67daedc86` through its native coding graph with
`deepseek/deepseek-flash`. The final local SDK run completes 1/1 input, returns a
local Judge pass, passes the quality gate and exits 0. Host trace validation and
container cleanup both succeed.

- [Case](smoke-case.json): create a one-statement Python file and execute it.
- [Original input](input.json), [Agent result](result.json),
  [SDK execution manifest](execution-manifest.json), and
  [local Judge report](judge-report.json) are copied without editing.
- [Acceptance summary](acceptance-summary.json) is a contributor-generated index
  with source revisions, run identities and SHA-256 hashes of those records.
  It is separate from the original SDK documents.

Complete original traces, the Judge request, network evidence and failed attempts
are retained locally. This bounded public package contains the original output
and report, rather than claiming to reproduce the whole trace archive. File and
shell calls are observed in the native trace; official KUMA file-change export
has not yet been exercised.

The pinned source restores from an empty directory and the installation overlay
loads correctly. Combined unit and catalog-based strategy validation pass. Seven
binding contract tests pass. The bundled `examples.offline_demo` and
`kuma quickstart` also pass; these deterministic checks are distinct from the
model-backed target smoke above.

## Reproduce the local target smoke

Install ABB and the KUMA host dependencies following the repository guide. Use
Docker and a Linux filesystem for container bind mounts (for Windows, the WSL
distribution's filesystem). Configure these names in the local ignored `.env`:

```dotenv
ABB_MODEL_PROVIDER=deepseek
DEEPSEEK_API_KEY=<your model key>
DEEPSEEK_MODEL=deepseek-flash
ABB_MAX_PARALLEL_CASES=1
ABB_MAX_PARALLEL_JUDGES=1
ABB_LOCAL_JUDGE_MAX_CHARS=250000
```

Enable only `mini-opencode` in your local registry, leaving its status as
`adapting`, then run from the ABB project root:

```bash
agentbench evaluate mini-opencode --sdk local \
  --case-file docs/validation/issue522-mini-opencode/smoke-case.json \
  --cases 1 --max-steps 1 --case-retries 0 --timeout 300 --no-view -y
```

The run uses the model API but no KUMA backend credits. Preserve the result paths
printed by the CLI. A local Judge pass covers this one Case only.

## Earlier attempts and next stage

The first Windows-mounted-directory attempt fails before inference with a bind
mount I/O error and a missing OpenTelemetry transport dependency. The target
Dockerfile now installs that dependency, and later runs use WSL ext4. An earlier
successful Agent execution receives an inconclusive local Judge result because
its full evidence exceeds the default 120000-character budget. That report is
retained; a separate assessment at 250000 characters passes. The final run uses
that limit from the start and completes the entire command successfully.

The KUMA account and current strategy catalog are verified. The selected group
is `basic-safety-coding@1`, catalog release
`43c0d76812c5ec2dafa097b82a6b7ba43343ac14c18065193734c090864604dc`.
No official Case generation or Judge calls were made. Phase-two GT work follows
the issue procedure after integration review/merge and credit allocation.
