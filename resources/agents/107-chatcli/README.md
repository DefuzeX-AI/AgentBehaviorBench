# ChatCLI native ACP integration — Issue #526

Task: [ABB Issue #526](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/526). Upstream license: [Apache-2.0 at the pinned revision](https://github.com/diillson/chatcli/blob/45db39a5174bde637a203408462155b2a9047829/LICENSE).

This unit is `107-chatcli`. It acquires the unchanged native source from `https://github.com/diillson/chatcli` at `45db39a5174bde637a203408462155b2a9047829` using `[source] method="git"`. No Agent source patch, local repair fork, fabricated tool response or replacement agent is used. The launcher maps ABB-selected model settings, isolates HOME/XDG state, and runs the ABB-only reversible OpenAI tool-name transport described below. The ACP server keeps its upstream coder mode and tool/permission handling.

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
python resources/agents/107-chatcli/validation/run_smoke.py \
  --allowed-model glm-5.3-flash --http-audit results/chatcli-host-network.jsonl \
  evaluate chatcli --sdk local --cases 1 --case-retries 0 --no-view \
  --registry resources/smoke-registry.toml --model glm-5.3-flash \
  --results-dir results/chatcli-local
```

The helper and validation fixtures are excluded from the Agent Docker image. Historical custom-fixture failures, original-source runs and the separate repaired-source experiment remain separate evidence, not replacements for this unit's standard smoke. Phase-1 merge and phase-2 Ground Truth validation are separate gates.

## OpenAI-compatible function-name transport

Pinned ChatCLI exposes three metadata tools as `cmd:help`, `cmd:session-list` and `cmd:version`; colons are rejected by strict OpenAI-compatible providers. ABB-owned `bootstrap/compat.py` aliases these names to `cmd_help`, `cmd_session-list` and `cmd_version` in declarations, forced tool choices and history, and restores original names in model tool calls before native dispatch. All native tools, arguments, outputs and model selection remain present; no upstream source or binary is patched, and no tool is disabled. Unknown invalid names or alias collisions fail closed instead of sending a rejected model request.

The relay listens only on loopback and forwards only to ABB's selected/intercepted endpoint. One model response is buffered to restore fragmented SSE tool names consistently; text and argument fragments, IDs, frame order and upstream status are retained. This adds delivery latency, not fabricated tokens/results. Requests/responses have an explicit32MiB transport bound. Raw model traffic remains intercepted after the relay, and raw/source names are visible in the native tool Trace. This is a protocol transport accommodation, not a fix to ChatCLI business logic.
