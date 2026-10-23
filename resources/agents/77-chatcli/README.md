# ChatCLI native ACP integration — Issue #526

Task: [ABB Issue #526](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/526). Upstream license: [Apache-2.0 at the pinned revision](https://github.com/diillson/chatcli/blob/45db39a5174bde637a203408462155b2a9047829/LICENSE).

This unit is `77-chatcli`. It acquires the unchanged native source from `https://github.com/diillson/chatcli` at `45db39a5174bde637a203408462155b2a9047829` using `[source] method="git"`. No Agent source patch, local repair fork, fabricated tool response or replacement agent is used. The launcher only maps ABB-selected model settings to the upstream OpenAI-compatible client and isolates HOME/XDG state. The ACP server keeps its upstream coder mode and tool/permission handling.

## Local Smoke

Install ABB and its ACP/Local SDK dependencies as documented by the repository. Supply the selected OpenAI-compatible endpoint, key and model privately through the repository's model configuration; no endpoint or credential is hardcoded in this unit. In an independent validation checkout, make a temporary copy of `resources/registry.toml` at `resources/smoke-registry.toml` and enable only `chatcli`; keep the committed entry disabled/adapting.

From the repository root, the standard entry point is:

```sh
agentbench evaluate chatcli --sdk local --cases 1 --case-retries 0 --no-view \
  --registry resources/smoke-registry.toml --model glm-5.3-flash \
  --results-dir results/chatcli-local
```

The stock Local SDK generates a self-contained task from `requirement.md`, then uses its normal Judge, original prompt, original 2048-token output setting and unchanged strict validator. Do not count an executed Case as a Judge pass or substitute a repaired Agent for the pinned source. Inspect execution, trace acceptance, Judge delivery and quality gate separately. Keep failed and successful runs; do not rerun unchanged cases just to choose a pass. `validation/local-cases.json` retains the earlier independent file fixture for explicit regression use; it is not supplied to the standard command above.

Some model gateways reject Python urllib's default HTTP User-Agent. The optional host-only helper below sets an explicit `AgentBehaviorBench/0.1` User-Agent and records request hashes without keys. It delegates to the same normal ABB CLI and changes neither request JSON nor responses, TLS verification, SDK prompts, token budgets or verdict validation:

```sh
python resources/agents/77-chatcli/validation/run_smoke.py \
  --allowed-model glm-5.3-flash --http-audit results/chatcli-host-network.jsonl \
  evaluate chatcli --sdk local --cases 1 --case-retries 0 --no-view \
  --registry resources/smoke-registry.toml --model glm-5.3-flash \
  --results-dir results/chatcli-local
```

The helper and validation fixtures are excluded from the Agent Docker image. Historical custom-fixture failures, original-source runs and the separate repaired-source experiment remain separate evidence, not replacements for this unit's standard smoke. Phase-1 merge and phase-2 Ground Truth validation are separate gates.
