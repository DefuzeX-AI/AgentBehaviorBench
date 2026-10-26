# OpenAEON native Gateway/ACP integration

Refs #527. Registry lifecycle and enabled state live in `resources/registry.toml`; configuration, image construction, Local Smoke and official GT are separate gates.

## Pinned source

`openaeon/OpenAEON@e9b35678fbacc9a2c018574b6731202228f8686d`, package2026.5.19, requires Node>=22.12.0 and pnpm10.23.0. The snapshot records7,758 regular files and two relative `CLAUDE.md` symlinks. ABB's current Git acquisition does not support that layout, so source acquisition is explicitly `bundled`. Supply an unchanged local snapshot and run:

```bash
python bootstrap/prepare_source.py /absolute/path/to/unmodified/OpenAEON
```

The preparer verifies all7,760 pinned entry hashes before copying and preserves both links. It never overwrites existing `agent/`. Keep original source ignored; commit provenance and outer inputs only. The normal ABB worker snapshot materializes in-tree file links; original regular source files remain unchanged. Native pnpm build outputs are generated normally, not hand-edited.

## Native execution and model selection

The outer launcher writes a private per-Case native configuration, starts original `openaeon.mjs gateway run`, and connects original `openaeon.mjs acp` over authenticated container loopback. ACP streams, engine, prompts, tools, bootstrap behavior, independent native approvals and errors remain upstream. Multiple steps share the same processes and state; Cases do not share private state. No daemon or public Gateway is installed.

Normal `ABB_AGENT_MODEL_*` runtime settings select one OpenAI-compatible text model, including main, delegated, heartbeat and image-model selection slots, without alternate model fallbacks. This is not an image-capability claim. No service or credential is pinned in the unit. Interactive heartbeat scheduling is disabled; native tools and other native services are not removed. Source and Profile enumerate deployment prerequisites and pending-approval behavior.

## Source build and startup caches

The outer recipe runs original frozen-lockfile `pnpm install` and `pnpm build` on pinned Node24. It omits the nonexistent `.npmrc` COPY input from the upstream Dockerfile, an unrelated UI build and optional browser installation. TLS, APT signatures and package integrity checks remain enabled. Dependency cache mounts change download reuse, not installed native features.

Cold native module loading exceeded the initial100second1CPU/1GiB preflight budget. A Node-only cache probe also exceeded180seconds. V8 profiling found native ESM compilation and Jiti/Babel traversal on the startup path. The build now warms the original Gateway in a network-disabled process with a dummy route and no model prompt. Public Node bytecode and Jiti filesystem transforms are stored outside runtime `/tmp` and copied into private per-Case directories. `JITI_FS_CACHE` is a boolean environment switch in installed Jiti2.6.1; use `true` with private `TMPDIR`, not an arbitrary pathname. The native loader is not patched.

Startup remains bounded at180seconds, ACP handshake at300seconds, and the overall runtime at900seconds. Normal ABB CPU/memory policy is unchanged. The build warm-up uses build resources; it is not a runtime resource acceptance result. Actual constrained runtime acceptance and the exact source SHA must be recorded separately.

## Evaluation

`requirement.md` is the KUMA Profile. The custom native-read fixture is under `fixtures/local-smoke/`; it tests a real native read of the installed package manifest, not shell execution, messaging, browsers or filesystem-preservation certification. Fixtures remain outside the image. Keep unsuccessful builds/preflights and strict Judge/evidence failures; do not relabel them or sample until a desired verdict appears. Official GT follows stage1 merge and the Issue's stated process.

The bridge explicitly selects a fresh `agent:main:abb-<random>` native session key. The upstream bridge default `acp:<uuid>` normalizes into the reserved external-ACP backend namespace at this pin; with external ACP dispatch unconfigured, it yields `ACP_DISPATCH_DISABLED` before any model invocation. Selecting the documented `--session` option routes to the original embedded main Agent; it does not enable a different backend, patch upstream dispatch, or remove tools. The original empty-answer Smoke and Judge issue remain separate from any post-fix acceptance.

## Native tool evidence

At this pin the original ACP Gateway connection does not advertise the Gateway `tool-events` capability, so its otherwise-present tool notification handlers do not receive those events. The outer launcher retains an exact byte copy of original ACP stderr while forwarding it unchanged. The configured existing ABB `evidence_reader` uses the original `newSession` mapping, private native session store and Pi session JSONL to retain actual assistant/tool-result records in framework evidence. It does not synthesize protocol tool events, provider response IDs, attempt counts or internal model spans. Original native IDs and raw records are retained; unmatched sessions, linked files and out-of-bound paths are rejected. Native transcript evidence is untrusted and is independently cross-checked against intercepted model calls during acceptance.
