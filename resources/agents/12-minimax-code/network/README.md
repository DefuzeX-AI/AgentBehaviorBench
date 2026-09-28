# MiniMax native network observation

The pinned upstream checkout under `../agent/` remains unmodified. The outer
`agent.toml` declares model routes and references `rules.toml` for other network
operations. ACP selects `observe` through its adapter; there is no user mode flag.

## Source contracts

- `bootstrap/native-config.yaml` selects the international API-key endpoint
  `https://api.minimax.io/anthropic` using the upstream `minimax_api.baseURL` field.
  Model messages use `/anthropic/v1/messages`. Native `minimax_api` counting
  selects `/v1/responses/input_tokens` even for Anthropic generation, as defined
  in `packages/local-runtime/src/context/token-counter-adapters/responses.ts`.
  An explicit auxiliary route permits that endpoint; the Anthropic count route
  is also declared. BBA observes counts unchanged without synthesizing a reply.
- `packages/tui/src/cli/provider-command.ts`: `provider set-minimax-key` saves the
  value from the named environment variable and selects `minimax_api_key` mode.
  The launcher calls this existing command, not a replacement model service.
- `packages/local-runtime-v2/src/service/model-system/catalog/provider-presets/`:
  the international runtime reads `https://models.dev/api.json` directly.
  Its metadata rule permits only that path, without the CN descriptor/CDN routes.
- `packages/local-runtime/src/content-safety/api-base.ts`: international production
  review starts at `agent.minimax.io`. The service can return an HTTP 307 redirect
  to `agent.minimaxi.com`, so both hosts permit only the same exact
  `/mavis/api/v1/content` POST path. The second route preserves the redirect's
  observable response instead of trusting a general cross-domain redirect.
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

The deployment now requires `MINIMAX_API_KEY` before execution. It does not
forward MAVIS_ACCESS_TOKEN or select the managed-login model route. The native
CLI writes the API key into a fresh private Case profile. Catalog and title-review
routes remain scoped and observable; a failed optional account operation is not
reported as a successful review. API authentication and complete certification
remain unverified until a real key is supplied and an actual Case completes.

## Updating upstream

1. Update the imported source and provenance, retaining outer adaptation files.
2. Compare native URLs, authentication, token counting and ACP startup contracts.
3. Run observation/replacement regressions and a real native smoke. Investigate
   unknown requests before adding narrowly scoped routes; do not allow entire hosts.
4. Run full SDK certification before marking the Agent ready.
