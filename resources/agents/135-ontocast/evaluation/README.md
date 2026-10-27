# Local Smoke evidence and reproduction

## Recorded run

The successful run described in [onboarding-2026-10-27.md](onboarding-2026-10-27.md) used one synthetic English document and completed with CLI exit 0. Its execution, trace validation and cleanup succeeded, and the local Judge returned pass/high with no findings or evidence gaps.

Review the saved records directly:

- [Executed Case and profile context](smoke-case.json).
- [Run record](evidence/execution/run.json) and [Agent output](evidence/execution/result.json).
- [Accepted Judge report](evidence/judge/report.json), [Judge transport usage](evidence/judge/transport.json) and [command receipt](evidence/run-receipt.json).
- [Source preparation record](evidence/source-verification.json), [binding-test transcript summary](evidence/binding-tests.json), [configuration validation record](evidence/combined-validation.json) and [runtime package versions](evidence/runtime-versions.json).
- [Earlier DeepSeek receipt](evidence/prior-ds-v9-receipt.json) and [failed Qwen-Long assessment receipt](evidence/prior-qwen-long-failure.json). These failures were not replaced by the later success.
- [Export manifest](evidence/export-index.json), including SHA-256 hashes of the committed copies.

These records are sanitized derivatives: local paths are replaced, credentials and private reasoning are excluded, and this directory is not an importable full SDK ledger. The original SDK result hash is recorded in `acceptance-summary.json`; the export manifest distinguishes it from the committed output copy's hash. The test transcript summary records an earlier observed result, rather than a new execution.

The successful run used unit directory `129-ontocast`. Registration was subsequently renamed to `135-ontocast` to avoid another merged Agent's number. The Dockerfile now explicitly downloads embedding snapshot `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, the same snapshot observed in that run. Its offline repository-name cache reference is fixed to this snapshot as well. That pin and the portable runner below were added after the successful run; no new Docker build or paid/model execution is claimed for this documentation update.

## Reproduce with Bailian in Linux or WSL

Use the ABB checkout's Python environment, with ABB and its local SDK dependencies installed and Docker available. Source preparation restores the pinned native source through `agent.toml`. Export the existing `DASHSCOPE_API_KEY` into this process using your normal secret mechanism; never commit it or put it in command-line arguments.

Before running, open the Beijing-region Bailian quota page for the **exact** model `qwen3.7-max-2026-06-08`, check its remaining quota and enable **free-quota-only / stop when exhausted**. The runner cannot inspect the account's billing setting. It does not enable that setting itself, and the confirmation flag is an acknowledgement by the operator. Agent and Judge inference consume model tokens; one prior Judge request used 332,374 tokens. Free quota availability can change. This does not consume official KUMA credits.

From the ABB repository root:

```bash
python resources/agents/135-ontocast/evaluation/run_bailian_local.py \
  --results-dir /absolute/path/to/new-ontocast-smoke \
  --confirm-free-only
```

The results path must not already exist. The script inherits process credentials, selects the [Bailian provider catalog](bailian-providers.toml), and runs the committed fixed Case with `--sdk local --cases 1 --max-steps 1 --case-retries 0 --timeout 900`. It limits Agent requests and elapsed time, preserves command output and a receipt, and allows only one Judge upstream request. Model request limits are a local guard; the account's free-quota-only setting supplies the billing protection.

The [Judge transport](bailian_judge_transport.py) uses the provider's `enable_thinking=false` and strict JSON schema for ABB's existing verdict fields. It does not require a passing verdict: pass, issue and inconclusive remain valid, and ABB applies its normal response and evidence validators. The original Judge messages and upstream response are preserved. Agent traffic uses normal ABB replacement interception and is not handled by this Judge transport.

The runner's portable paths, result layout and process-only environment setup differ from the original machine-local launcher. The selected model, provider endpoint, Case, ABB evaluation arguments and Judge settings are retained. A new execution may produce a different outcome. This is local Smoke, with no GT finding or official KUMA assessment claimed.
