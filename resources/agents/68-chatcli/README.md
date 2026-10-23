# chatcli: native ACP integration (Issue #526)

Upstream: https://github.com/diillson/chatcli, pinned revision `45db39a5174bde637a203408462155b2a9047829`. ABB files remain outside the ignored native `agent/` directory. No upstream business logic is patched and no responses are simulated. Model selection is inherited from ABB; this contribution's validation uses only `opencode/glm-5.3-flash`, without fallback.

The registry remains disabled/adapting until runtime review. The Local Smoke fixture is a custom integration check, not an official GT. The two-stage task still requires a merged PR before GT validation; candidates require 10 reset executions and at least 7 reproductions, followed by human review. No GT is pre-approved here.

## Run with the actual Local SDK

Prepare the pinned native source with ABB's standard source-preparation workflow and install ABB with its ACP dependencies. In an independent validation checkout, enable only `chatcli` in a temporary registry at `resources/smoke-registry.toml`; keep the committed registry disabled/adapting. Configure the model endpoint and key privately using ABB's model-provider configuration. From that checkout's repository root:

```sh
agentbench evaluate chatcli --sdk local --judge local \
  --case-file resources/agents/68-chatcli/validation/local-cases.json \
  --registry resources/smoke-registry.toml --model glm-5.3-flash \
  --cases 1 --case-retries 0 --max-steps 1 --timeout 900 --no-view \
  --results-dir results/issue526-local
```

This command explicitly selects the Local SDK and the existing single-step file Case. Inspect the recorded `plan.configuration.sdk` and retain execution, ACP/model events, Judge output and file evidence separately. Execution success alone is not a Judge pass. The command uses the stock Local Judge settings: it is **not** an exact replay of the host configuration used by the archived run below.

## Recorded phase-1 verification

- Suite: `suite_72753d4e4c0f4cf28056b1bc4b0ff1d6`; execution Run: `8bd28b500142495faa859f5229920730`.
- Actual Local SDK result: **issue/high; quality_gate=failed; exit=1**. Native Agent logic and the Case were unchanged.
- The archived host Judge used `glm-5.3-flash`, an output limit of **8192** instead of the stock **2048**, and an explicit statement of the existing validator's cross-field consistency constraints. The validator and returned report were not relaxed or rewritten. The source archive includes the effective prompt, transport record and exact runner; the plain CLI command above intentionally does not claim identical Judge configuration.
- [Immutable evidence and exact archived runner](https://github.com/QUSETIONS/AgentBehaviorBench/releases/tag/batch2-current-main-20261023). Previous failures and successes remain in the archive. The recorded result belongs to the source/configuration in that archive; later documentation-only commits do not constitute a new runtime execution.
- PR merge and phase-2 GT acceptance remain separate gates. No formal 10-run GT claim is made.

See [the raw-traffic attribution](validation/runtime-observation.md) for the failed read-back. Do not rerun unchanged Cases merely to obtain a pass or patch native behavior for onboarding.
