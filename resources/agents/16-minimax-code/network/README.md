# MiniMax native network observation

The pinned upstream checkout under `../agent/` remains unmodified. The outer
`agent.toml` declares model routes and references `rules.toml` for other network
operations. ACP selects `observe` through its adapter; there is no user mode flag.

## Source contracts

- `packages/config/src/config.ts`: the CN production managed preset uses
  `https://agent.minimax.cn/mavis/api/v1/llm/v1`. Model messages are forwarded
  unchanged, including native authentication and model selection.
- `packages/local-runtime/src/context/token-counter-adapters/messages.ts`:
  token counting appends `/v1/messages/count_tokens` to the model base URL.
  Explicit count routes cover this form and a base normalized to one `/v1`.
  Requests and responses remain native; BBA does not synthesize counts in observe.
- `packages/local-runtime-v2/src/service/model-system/catalog/provider-presets/`:
  the CN descriptor resolves a versioned catalog on `filecdn.minimax.chat`.
  Both requests have independently scoped rules.
- `packages/local-runtime/src/content-safety/api.ts`: review sends the original
  `content_text` and `scene`. Responses, including rejection and HTTP 401, reach
  the Agent unchanged. The Agent owns fallback behavior. This route is optional
  for host evidence acceptance because title generation can run independently
  from the main task; it does not mean review succeeded or was bypassed.

## Credentials and acceptance

The previous replacement smoke (`94646a37c70e407d9d5d4519e69d7b56`) completed
three model request/response pairs and fetched catalogs with HTTP 200. Its local
counts and substituted OpenRouter model describe the old implementation, not
native observation acceptance. Its scene-205 title review returned HTTP 401,
`token is required`. No successful review was synthesized.

`MAVIS_ACCESS_TOKEN`, when supplied, is forwarded unchanged. It is no longer a
mandatory preflight secret merely because title review may read it. Current
upstream managed authentication also uses runtime auth context; supplying that
one variable alone is not proof of a working native login. The unit stays
`adapting` until a real native certification is retained.

## Updating upstream

1. Update the imported source and provenance, retaining outer adaptation files.
2. Compare native URLs, authentication, token counting and ACP startup contracts.
3. Run observation/replacement regressions and a real native smoke. Investigate
   unknown requests before adding narrowly scoped routes; do not allow entire hosts.
4. Run full SDK certification before marking the Agent ready.
