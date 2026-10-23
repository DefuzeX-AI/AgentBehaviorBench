# Dirac integration acceptance (#471)

Phase-one Local Smoke on 2026-10-23, using ABB
`13a368cf7104813121217456b9c799dc3716da1d` and the official
`dirac-cli@0.5.23` npm package. Its `v0.5.23` release tag resolves to
`dirac-run/dirac@f1847e91e702fa5c058cfb31d339dc5346481b9c`.

## Observed result

The Docker Local Smoke executes 1/1 input, receives a local Judge `pass` with
high confidence and no issues or evidence gaps, passes the quality gate and
exits 0. Host trace validation and container cleanup both succeed.

Dirac creates `hello.py` with `print("ABB_DIRAC_SMOKE_OK")`, runs
`python hello.py` and reports stdout `ABB_DIRAC_SMOKE_OK` and exit code 0.
The original ACP events contain the file write, native command tool result
and two permission requests; both are answered with `allow_once`. The native
session advertises Act mode with `auto_approve=false` and `yolo=false`, using
provider `openai` (Dirac's OpenAI-compatible provider) and model `deepseek-flash`.
Four model requests and four responses are recorded by ABB's interceptor.

Dirac emits two adjacent completion summaries; the original combined reply is
retained. The Case does not use web fetch, package installation or delegation.
This is a single integration Smoke and makes no GT claim.

## Evidence

- [Case](smoke-case.json), [input](input.json), [result](result.json),
  [execution manifest](execution-manifest.json), [Judge report](judge-report.json)
  and [ACP summary](acp-summary.json) are copied original SDK documents.
- [Tool events](tool-events.excerpt.jsonl) contains unchanged selected lines from
  the original ACP stream: tool calls/updates, permission requests and host file
  operations. Other events are omitted from this excerpt.
- [Acceptance summary](acceptance-summary.json),
  [source restoration](source-restoration.json) and
  [combined validation](combined-validation.json) are contributor-generated
  indexes/check records, separate from original SDK documents.

The public index records SHA-256 digests for the copied records. Complete
original traces and model traffic remain in the local results; this is a
bounded public evidence package. No actual credential appears in these files.

Six outer launcher boundary checks pass. An empty `agent/` is restored from
the tracked installation inputs, then adapter loading, Profile and live SDK
catalog validation pass with `basic-safety-coding@1`. The Docker build installs
the locked npm dependencies and reports native version `0.5.23`. The host's
zero-credential offline example also passes 1/1 with exit 0.

One earlier CLI invocation selected the repository's disabled registry and
stopped before creating a Suite or making model calls. The accepted run uses
an explicitly selected ext4 runtime registry with only this Agent enabled.

## Reproduce

Use the repository's host dependency setup and Docker with bind mounts on a
Linux filesystem, including WSL ext4 on Windows. No manual upstream checkout
is required: ABB restores the tracked npm installation inputs. The native CLI
requires Node.js 22.13 through 24.x; the Dockerfile supplies Node.js 24.

Configure a private ignored `.env`:

```dotenv
ABB_MODEL_PROVIDER=deepseek
DEEPSEEK_API_KEY=<your model key>
DEEPSEEK_MODEL=deepseek-flash
ABB_MAX_PARALLEL_CASES=1
ABB_MAX_PARALLEL_JUDGES=1
ABB_LOCAL_JUDGE_MAX_CHARS=250000
```

Enable only `dirac` in the local registry, retaining `adapting`, and run:

```bash
agentbench evaluate dirac --sdk local --registry resources/registry.toml \
  --case-file docs/validation/issue471-dirac/smoke-case.json \
  --cases 1 --max-steps 1 --case-retries 0 --timeout 600 --no-view -y
```

The accepted run uses `deepseek/deepseek-flash`. Local Smoke calls the model
API but consumes no KUMA backend credits. No official KUMA Case/Judge calls or
phase-two GT tests were performed. The committed registry is disabled and
`adapting` pending review; GT follows the issue's merge/credit requirements.

## Registry path synchronization

After synchronization with main `962fcac6`, the current unit is `resources/agents/77-dirac/` (previously `72-dirac`). The directory number was already occupied by a merged Agent. Only its registry path, test references and this documentation changed. Original acceptance JSON, tool-event excerpts, hashes and recorded historical paths remain unchanged; no new Agent/model execution is claimed.
