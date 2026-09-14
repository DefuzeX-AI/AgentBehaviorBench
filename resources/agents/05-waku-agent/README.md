# 05 Waku Agent

Status: **adapting**. The source and offline boundary are verified; no live model,
web-search, Case generation, Judge, certification, or benchmark run is claimed.

Source: [ShenSeanChen/waku-agent](https://github.com/ShenSeanChen/waku-agent),
official `main` at `a2fb2563ebeacf65596a34e6a73cfedb040f8a1b`, downloaded
2026-09-14. A fresh clone on that date had the same HEAD. The vendored source,
apart from the declared ABB graph file, compared byte-for-byte with that clone.
This is newer than wangyi's earlier pin `21486b39ca2b59cf3a616159139712f4bef0914c`.

The code is MIT. Waku marks and named brand assets have their separate
`LICENSE-BRAND`, and bundled fonts retain SIL OFL 1.1 notices. All license files
remain in `agent/`. `source-manifest.json` records all 310 upstream files and
their SHA-256 digests. No nested Git metadata is vendored.

## Native boundary

`bindings/waku_binding.py` creates one upstream `waku.app.Waku` instance for a
Case, backed by a fresh private Waku home and its native SQLite connection. Each
Input is passed unchanged to the public `Waku.respond(message, source="cli",
stream=False)` lifecycle. The same native instance owns working history, semantic
and episodic memory, local tools, tracing, and consolidation across Inputs in that
Case. ABB never concatenates a transcript or inserts memory. Closing the Case
closes the native app and database and removes its private home.

The accepted boundary is a non-empty string or exactly `{"message": "..."}`.
Attachments, caller-supplied histories, extra fields, and blank values are
rejected before native dependencies load. The binding returns the complete
native `LoopResult` as `reply`, `tool_calls`, and `iterations`; the whole object
is the SDK-facing output and raw evidence.

The enabled native tools can create and list records in the Case-local calendar,
save facts, create local message drafts, search through DuckDuckGo, and manage
Waku's local memory and skills. Apple/Google integrations, GitHub, gateways, MCP,
experimental delegation, and Tavily are explicitly disabled. A local draft is
not a sent message, and a local calendar row is not a cloud calendar change.

## Reproducible deployment

`agent/abb-langgraph.json` is the only file added inside the upstream tree. It
names Waku's public application class so ABB can validate the unit layout; the
outer binding performs the invoke-compatible translation. All other onboarding
files live outside `agent/`.

The Dockerfile uses Python 3.13 and installs the hash-locked
`dependencies.lock`, generated from the unchanged upstream project plus the
small ABB runtime requirements. It then builds the upstream package without
dependency resolution and runs the worker as UID 10001. Model traffic is fixed
to the declared OpenAI Chat Completions route. DuckDuckGo is the only non-model
outbound route.

The ABB worker-overlay image built successfully on arm64. A network-free
container check imported the native Waku package and exercised binding creation,
input validation, and cleanup without using a provider key. Live model/tool
execution and certification remain outstanding.

`evaluation/input-contract.json` is the exact identity contract. The verified
catalog group is `BASE-06@1` (Workflow Assistant). See `requirement.md` for the
remaining live-service checks. Offline tests are in
`tests/test_onboarding_waku_article.py`.
