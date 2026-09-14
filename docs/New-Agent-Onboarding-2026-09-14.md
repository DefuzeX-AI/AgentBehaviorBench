# Waku and Article Explainer Onboarding Record — 2026-09-14

This record covers the source-import and offline-adapter stage for two new Agent
units. Both are registered with `enabled = true` and `status = "adapting"`.
Onboarding did not run paid Case generation, a Judge, `agentbench certify`, or
promote either unit to `ready`.

## Source and native boundary

| Registry ID | Official source and fixed revision | Native call boundary |
| --- | --- | --- |
| `waku-agent` | [ShenSeanChen/waku-agent](https://github.com/ShenSeanChen/waku-agent) at `a2fb2563ebeacf65596a34e6a73cfedb040f8a1b` | One upstream `waku.app.Waku` instance and private Waku home per Case. Each current Input is passed to public `Waku.respond(message, source="cli", stream=False)`; Waku owns conversation, SQLite memory and tool state. |
| `article-explainer` | [duartecaldascardoso/article-explainer](https://github.com/duartecaldascardoso/article-explainer) at `2cf067dc4b9158b03361c7b3e2544e067b75f1ae` | The binding invokes the compiled upstream `explainer.graph.app` with the current message and returns the complete native `SwarmState`, including messages and `active_agent`. The five upstream specialists coordinate through their native handoffs. |

Waku is newer than the revision recorded in the earlier wangyi material. Article
Explainer matches wangyi's fixed revision. Both repository URLs were available
in wangyi, so no inferred or name-matched repository was used.

## Outstanding live work

| Registry ID | External dependencies and certification blockers |
| --- | --- |
| `waku-agent` | Intercepted OpenAI Chat Completions credentials and, for web Cases, exact DuckDuckGo access. Native model/tool traces and Case isolation still need live acceptance. |
| `article-explainer` | Intercepted OpenAI Chat Completions credentials and live traces proving model calls and specialist handoffs remain native. Each Input must carry its complete article excerpt because the graph has no headless document store or checkpointer. |

## Verification completed

Each repository was cloned at the fixed revision into a separate download
directory. The vendored `agent/` tree was checked path by path against the
official checkout, including file content digests. Upstream tracked files remain
unchanged. The only declared source-tree addition is `agent/abb-langgraph.json`;
bindings, Docker configuration, Profiles, requirements and deployment notes live
outside the upstream tree. Source manifests retain repository, revision, license
and per-file SHA-256 evidence. Nested Git metadata was not vendored.

Offline checks cover registry loading, manifest and Profile parsing, exact input
contracts, adapter discovery, public native call seams, native result forwarding,
Case lifecycle and cleanup, source pins, licensing and Docker unit structure.
Focused onboarding verification completed with **24 passed**. The full repository
suite completed with **495 passed, 11 skipped**; the skipped checks are existing
opt-in integration tests.
These checks use controlled fakes only at the external/native seam; they do not
replace production code paths and do not establish live runtime readiness.

Both ABB worker-overlay images built successfully with Docker Desktop on arm64.
Network-free container checks imported the native modules and exercised binding
creation, input validation and cleanup without allowing a provider request:

| Registry ID | Local image manifest ID |
| --- | --- |
| `waku-agent` | `sha256:70cd8c31f45926ba2cce8ec2796253c460d97cf22fdf829e01463eb61aceab11` |
| `article-explainer` | `sha256:908a3b30df4e78390f1ccbeef7af306596f62816cd43f1e2643b20f8b2f83bd7` |

No provider key was consumed by this onboarding stage. No model, Case generator
or Judge was contacted. A real `observe`, live smoke run and `certify` remain
required before either registry status can become `ready`.
