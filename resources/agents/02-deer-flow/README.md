# 02 — DeerFlow

## Source checkout

- Upstream: https://github.com/bytedance/deer-flow
- Source: `agent/` (upstream tracked files, unchanged; nested `.git` removed so ABB tracks the source directly)
- Branch at clone time: `main`
- Commit at clone time: `0d4925305a6330a3442dcd336ed25750aea87cbd`
- Clone date: 2026-09-09
- Existing local reference: `wangyi/agents/tested/002_bytedance__deer-flow/` under the ABB workspace.

Status: downloaded only; not registered or certified in AgentBehaviorBench.
Dependencies have not been installed and the Agent has not been executed here.
This checkout follows upstream main; the historical tested record does not
establish that it used this same commit.

## Notes for the next onboarding step

Read the existing reference's `agent.md`, `runtime/README.md`,
`runtime/meta.json`, and `runtime/entrypoint.py` alongside the current upstream
backend. The historical integration accepts a `query` and calls a graph with
`ainvoke`. Its notes report DuckDuckGo TLS failures and recursion exhaustion;
revalidate tool requirements against this checkout before choosing a search provider.

Follow `docs/Agents/Layout.md` in AgentBehaviorBench: retain upstream source in
`agent/`, and place future ABB manifests, Docker build instructions, requirements,
and any Agent-specific bindings outside it. Reconcile the historical wrapper
with the current ABB runtime, model interception, and observation contracts
before registering the Agent as adapting and performing validation.
