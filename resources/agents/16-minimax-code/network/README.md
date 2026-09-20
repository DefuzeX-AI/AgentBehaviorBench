# MiniMax network adaptation

The pinned upstream checkout under `../agent/` is unmodified. `rules.toml` is an
outer BBA configuration referenced by `agent.toml`; the Dockerfile copies it into
the worker. BBA passes validated data to its interceptor, not Agent Python code.

## Source contracts

- `packages/local-runtime/src/context/remote-token-counter.ts`: remote counting
  falls back to the native BPE estimator; a 404/405 disables that remote endpoint
  for the process. Any successful count is labelled `remote` by the native client,
  including a locally intercepted reply. BBA records the actual `local_estimate`
  provenance, target model, encoding, algorithm version and request digest.
- `packages/local-runtime/src/context/token-counter-adapters/responses.ts`: the
  BYOK chat deployment uses the Responses input-token endpoint and reads the
  top-level `input_tokens`. It reuses BBA's standard protocol implementation.
- `packages/local-runtime-v2/src/service/model-system/catalog/provider-presets/`:
  the CN descriptor resolves a versioned catalog on `filecdn.minimax.chat`.
  Both outbound requests have independently scoped rules. Catalogs are forwarded,
  not replaced with a fabricated model list.
- `packages/local-runtime/src/content-safety/api.ts`: the original content review
  sends `content_text` and `scene`. BBA forwards the original operation and verdict.
  A `pass:false` body remains an Agent policy outcome. `required=true` means any
  observed HTTP/transport failure or missing terminal response rejects acceptance;
  this deployment intentionally does not claim full readiness after such a failure.

## Updating upstream

1. Import/checkout the new source revision and retain the outer adaptation files.
2. Compare these native contracts, package/runtime requirements and ACP startup.
   Update the manifest/source provenance and frozen dependency build if necessary.
3. Run the network service and host regressions, then the actual ACP smoke task.
   Check unknown requests instead of broadening the whitelist to a whole host.
4. Run full SDK certification before setting the registry to `ready`.

Local counting is opt-in and approximate. The configured encoding map names actual
BBA target models; unlisted models and media return an explicit unsupported response
so MiniMax can use its native fallback. Estimates never replace generation usage or
billing. No tokenizer or remote data is downloaded while answering a counting call.

## Current real-run finding (2026-09-20)

Run `94646a37c70e407d9d5d4519e69d7b56` returned local estimates 3217 and 11171,
completed 3 generation request/response pairs, and fetched both descriptor and CDN
catalog with HTTP 200. The native review request contained `scene: 205` and a
session-title string; the upstream replied HTTP 401, `token is required`.
`MAVIS_ACCESS_TOKEN` was absent. OpenRouter credentials do not authenticate this
MiniMax service. Put a valid native login access token in the local `.env` if this
workflow should complete; it is declared as a required tool secret and never committed. Missing credentials
now fail during setup, before a paid model call.
The unit remains `adapting`. No content-review success has been synthesized and no
full SDK certification is claimed. The original code intentionally treats title
work as detached from the main task; this deployment's strict `required` rule still
reports the missing native service authentication instead of hiding it.
