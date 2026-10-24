# pydantic-deepagents public-API ACP integration — Issue #473

Source: [vstorm-co/pydantic-deepagents](https://github.com/vstorm-co/pydantic-deepagents), commit `650b592b6accd7dc994226abbaa0cf717527e457`, distributed as the SHA256-pinned `pydantic-deep==0.3.50` wheel. All 615 non-dist-info wheel files match the fixed Git tree. The original installed library, Agent factory, tool implementations, model prompts and reasoning loop are unmodified. Registration remains disabled/adapting until review; GT starts only after merge/Credit confirmation.

## Explicit transport boundary

The upstream optional `apps.acp.server.DeepAgentACP` frontend reads an obsolete `FunctionToolResultEvent.result` field. Supported PydanticAI 2.52.0 and 2.60.0 events expose `part`, not `result`. This integration **does not patch that server, alias its event fields, or claim the upstream frontend is repaired**.

`bootstrap/bridge.py` is an ABB-owned text ACP transport around the native public [`Agent.run(..., event_stream_handler=...)` API](https://ai.pydantic.dev/api/agent/). `bootstrap/server.py` keeps the documented `create_deep_agent(model=..., workspace=LocalWorkspace(cwd), context_discovery=True)` factory, native `DeepAgentDeps`, and the same native per-run `ConfinedWorkspace(Workspace(LocalWorkspaceBackend(...)))` as the upstream example. The event ABI is explicitly pinned to `pydantic-ai-slim==2.60.0`, within the upstream `>=2.52.0` constraint.

The native Agent runs its own complete model/tool loop. The bridge only forwards text, passes native dependencies/workspace/history, observes actual native tool calls/results via `event.part`, and returns the native final text. Tool arguments and full results are retained without the upstream frontend's 500-character display truncation. A fresh native Agent/workspace is created per prompt, as in the upstream callable factory; native dependencies and message history persist within one Case but not across independent sessions. Native exceptions propagate as failed requests; cancellation returns `cancelled`, not successful completion. Unsupported non-text/MCP input and fallback model selection are rejected explicitly.

The bridge adds no tool implementation or interactive approval UI. Native workspace, tool checks and error/retry behavior remain in the original library. The ACP `allow_once` client setting applies only if a server asks for ACP permission; it is not evidence that this bridge has an additional approval gate.

## Standard validation

Privately configure the selected endpoint/key, install ABB and its ACP/Local SDK dependencies, and use normal source preparation. This package-based unit durably installs from outer `install/requirements.txt` in `/opt/agent-venv`; optional Agent dependencies do not enter ABB's host interpreter. In an independent validation checkout, enable only this Agent in a temporary copied registry; keep the committed registry disabled/adapting.

```sh
agentbench evaluate pydantic-deepagents --sdk local --judge local \
  --cases 1 --case-retries 0 --model glm-5.3-flash \
  --registry resources/smoke-registry.toml --timeout 900 --no-view \
  --results-dir results/pydantic-deepagents-local
```

This normally generates a Case from the Profile. A generated Case can be frozen and reused explicitly with `--case-file` after a genuine infrastructure fix; retain every prior attempt and explain the change. Do not select easier questions or substitute a repaired Agent fork. The historical custom fixture under `validation/` is not an automatic generated Smoke or a GT.

Some inference gateways require a declared HTTP User-Agent. The optional host-only `validation/run_smoke.py` delegates to the normal CLI, preserves bodies/responses/TLS/Judge rules, and audits selected-model request hashes without keys. Use only the approved `glm-5.3-flash` model; there is no fallback. Keep the stock Judge prompt, 2048-token output cap, 120000-character guard and strict validator unchanged.

Archive the exact validation commit, source and dependency versions, declared/effective Docker recipe, Case, actual output, host acceptance, Judge result and complete trace from one real run as required by [#109](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/109). An offline transport fixture, build or file write alone is not real Smoke acceptance. Native frontend failure, ABB integration failure, API/network errors and proven Agent behavioral defects remain separate outcomes. No formal GT result is claimed by this integration.
