# easy-agent native ACP integration — Issue #476

Task: [ABB #476](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/476). Source: [ConardLi/easy-agent](https://github.com/ConardLi/easy-agent), pinned to `aec616a97114ce9683e4fbfcff3abbc55155fe50`. Native source is restored under ignored `agent/`; the launcher, Docker recipe, Profile, native tools and permission handling are not patched for validation. Model settings come from ABB, never a hardcoded key or fallback model.

## Standard Local SDK Smoke

Install ABB and its ACP/Local SDK dependencies, then use the normal source-preparation workflow. Privately configure the model endpoint/key. In an independent validation checkout, copy `resources/registry.toml` to `resources/smoke-registry.toml` and enable only `easy-agent`; keep the contribution's registration disabled/adapting. From the repository root:

```sh
agentbench evaluate easy-agent --sdk local --cases 1 --case-retries 0 \
  --registry resources/smoke-registry.toml --model glm-5.3-flash \
  --timeout 240 --no-view --results-dir results/easy-agent-local
```

This uses the stock Local SDK to generate a task from `requirement.md`, then its stock Judge prompt, 2048-token output setting and strict validator. It does not import the historical Case fixture. Verify actual tool results, completed execution, host acceptance, trace validation, Judge delivery and quality gate separately. An executed Case or written file alone is not a Judge pass. Keep failed and successful runs; do not repeat unchanged cases just to choose a pass.

Some model gateways reject Python urllib's default HTTP User-Agent. The optional host-only helper below declares `AgentBehaviorBench/0.1` and audits selected-model request hashes without keys. It delegates to the same ABB CLI, preserving request bodies, responses, TLS verification, Judge prompt/token limit and verdict validation:

```sh
python resources/agents/78-easy-agent/validation/run_smoke.py \
  --allowed-model glm-5.3-flash --http-audit results/easy-agent-host-network.jsonl \
  evaluate easy-agent --sdk local --cases 1 --case-retries 0 \
  --registry resources/smoke-registry.toml --model glm-5.3-flash \
  --timeout 240 --no-view --results-dir results/easy-agent-local
```

The helper and validation fixtures are excluded from the Agent Docker image. Record the validation commit, environment and the Case/output/Judge/trace from one actual run as required by [#109](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/109).

## Historical evidence and task stages

The earlier imported file Case remains at `validation/local-cases.json` for explicit regression use. Its archived Judge used 8192 output tokens and added the existing cross-field consistency constraints, unlike the stock 2048 configuration above. [Historical runs and exact archived runner](https://github.com/QUSETIONS/AgentBehaviorBench/releases/tag/batch2-current-main-20261023) remain separate evidence and do not replace final-commit standard validation. No historical failure, returned report or native response is rewritten.

Phase 1 requires integration, real Local Smoke and PR merge. Phase 2 GT starts after merge/Credit confirmation under the Issue's independent-reproduction rules. A standard Smoke is not a defect-free or GT-completion claim.
