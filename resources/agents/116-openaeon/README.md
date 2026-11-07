# OpenAEON native Gateway/ACP integration

Refs #527. Registry lifecycle and enabled state live in `resources/registry.toml`; configuration, image construction, Local Smoke and official GT are separate gates.

## Pinned source

`openaeon/OpenAEON@e9b35678fbacc9a2c018574b6731202228f8686d`, package2026.5.19, requires Node>=22.12.0 and pnpm10.23.0. The snapshot records7,758 regular files and two relative `CLAUDE.md` symlinks. ABB's current Git acquisition does not support that layout, so source acquisition is explicitly `bundled`. Supply an unchanged local snapshot and run:

```bash
python bootstrap/prepare_source.py /absolute/path/to/unmodified/OpenAEON
```

The preparer verifies all7,760 pinned entry hashes before copying and preserves both links. It never overwrites existing `agent/`. Keep original source ignored; commit provenance and outer inputs only. The normal ABB worker snapshot materializes in-tree file links; original regular source files remain unchanged. Native pnpm build outputs are generated normally, not hand-edited.

## Native execution and model selection

The outer launcher writes a private per-Case native configuration, starts original `openaeon.mjs gateway run`, and connects original `openaeon.mjs acp` over authenticated container loopback. The engine, prompts, tools, bootstrap behavior and independent native approvals remain upstream. The outer ACP relay translates only the exact original high-risk code-edit confirmation error into an explicitly labelled refusal response; it does not confirm the edit, execute the rejected request, or alter other native responses. This refusal is not a successful code-writing result. Multiple steps share the same processes and state; Cases do not share private state. No daemon or public Gateway is installed.

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

For this pinned bridge, the upstream ACP stream can omit part of the final message. The unit-owned evidence reader offers an opt-in recovery hook to the generic ACP adapter: only a same-session, current-turn, original assistant record with a normal stop and verified text can supply the final result; thinking and tool-call blocks are not returned. Raw ACP updates are retained, and `native_output_recovered` records the recovery and raw-output hash. If the native identity or content checks do not match, no replacement is made. This is an integration recovery, not a change to the native source or proof that its ACP stream was complete.

## Owned-process cleanup

A retained post-routing Smoke invoked the real model twice, read the original package manifest, and returned native text, but failed the SDK cleanup gate before Judge delivery. The original outer supervisor stopped two native groups serially with eight-second grace periods, exceeding ACP's three-second cleanup budget. The supervisor now signals both owned groups together, allows a shared one-second TERM grace, kills remaining group descendants, and reaps them within one further second. This changes outer process ownership only, not native task execution or SDK validation. Offline actual-image cleanup and a fresh bounded Smoke must pass before submission; the failed run is not acceptance or GT.

## Runtime-UID cache identity

Node24 partitions its compile cache by Node/V8/architecture **and UID**. A root-generated seed ending in `-0` is not selected by the final UID10001; making it world-readable does not make its namespace reusable. The build now creates the normal final user before warm-up and runs the original native warm-up as that user. No cache directory is manually renamed and no Node validation is bypassed. The helper verifies that every generated namespace belongs to UID10001. A retained build reached Gateway readiness but its native shutdown exceeded30seconds, so a clean-exit assumption is not sufficient. A temporary build-only preload now handles a private SIGUSR2 request by calling [Node's documented synchronous `module.flushCompileCache()` API](https://nodejs.org/api/module.html#moduleflushcompilecache) and writing a PID/UID/cache-path receipt. The helper requires that receipt and nonempty cache files before allowing bounded cleanup to kill a lingering build process; it records forced cleanup explicitly rather than calling it a clean exit. This temporary preload and signal hook are deleted with the build state and never loaded by the production launcher. Native module source, tools, model prompts and native SIGTERM handling are unchanged; production ACP cleanup remains on the separate short bounded supervisor path. The prior cold-start failures remain retained, and fresh actual-image/real-Smoke acceptance is recorded separately.

## Build-only ACP loader warm-up candidate

The build-only cache warmer starts the pinned native ACP client against its private native Gateway and completes only ACP initialize and new-session requests before flushing each process's compile cache. It sends no prompt or model request. A build fails if either handshake or flush fails; the temporary build session and identity are discarded. Runtime Gateway settings, handshake timeout, native source, approval guard, workspace and 1 CPU/1 GiB limit are unchanged. This cache warm-up is a startup candidate and must be validated by a real Local Smoke.

The isolated 1 CPU / 1 GiB handshake trial also used a 512 MiB V8 old-space cap rather than 384 MiB; the Docker memory limit itself was not raised. One passing handshake does not establish startup reliability, complete tool behavior, or Judge acceptance.
