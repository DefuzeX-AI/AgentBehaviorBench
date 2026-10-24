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

## Controller shutdown compatibility

The controller close acknowledgement previously had a 10-second cap, shorter than the ACP adapter's possible 14-second close budget. The shared channel now allows at most 60 seconds, still bounded by a shorter configured runtime timeout. A zero-model protocol regression covers a valid acknowledgement after 12 seconds and a never-acknowledged timeout. This does not change native Agent logic, task inputs, model selection, Judge prompts, token limits or acceptance checks. Exact archived executions use the bundle's frozen Case and recorded command rather than generating a different task.

## Full-evidence Local Judge presentation

The shared Local Judge now offers a lossless JSONL view: adjacent events inherit
identical nested `common_fields`, while every distinct field, timestamp, event
order, text chunk and tool result stays present. The view is used only when smaller
than the original text and when every JSON record round-trips exactly. Original
attachment bytes and hashes remain unchanged. The exact model-facing view is
retained at `evaluation/judge/local-evidence-view.json`. This is a shared SDK input
presentation change, not an upstream Agent patch or a changed judging criterion;
it requires review along with the integration.

The existing 120000-character guard, Judge system prompt, 2048-token reply budget,
strict verdict validation and full-evidence hash validation remain unchanged.
Unique oversized evidence still returns `inconclusive` before any model call.
The prior frozen run's 225714-character evidence presents as 98703 characters with
all 313 framework events and four spans independently restored. That offline
round-trip audit is not itself a Smoke/Judge pass; retain a fresh final-head
container run and its real Judge response separately. Earlier `inconclusive`
reports are not replaced or edited.

## Historical evidence and task stages

The earlier imported file Case remains at `validation/local-cases.json` for explicit regression use. Its archived Judge used 8192 output tokens and added the existing cross-field consistency constraints, unlike the stock 2048 configuration above. [Historical runs and exact archived runner](https://github.com/QUSETIONS/AgentBehaviorBench/releases/tag/batch2-current-main-20261023) remain separate evidence and do not replace final-commit standard validation. No historical failure, returned report or native response is rewritten.

Phase 1 requires integration, real Local Smoke and PR merge. Phase 2 GT starts after merge/Credit confirmation under the Issue's independent-reproduction rules. A standard Smoke is not a defect-free or GT-completion claim.
