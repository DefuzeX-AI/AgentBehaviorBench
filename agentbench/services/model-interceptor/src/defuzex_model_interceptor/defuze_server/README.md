# Defuze model gateway

This target forwards Agent model requests using `KUMA_API_KEY`. It does not run
KUMA Case generation or Judges. The bundled host catalog selects `defuze_server`
by default; set `ABB_MODEL_PROVIDER=openrouter` (or another provider) to opt out.
Missing credentials and failed permission checks never select another provider.

Host configuration:

- `KUMA_BASE_URL`: server origin and API prefix, default
  `https://defuzex.ai/api/agentdefuze` (HTTPS only).
- `DEFUZE_MODEL_FAMILY`: `deepseek` (default) or `minimax`.
- `DEFUZE_MODEL`: defaults to `deepseek-flash` or `minimax/minimax-m3` respectively.
  `--model` and `ABB_MODEL` keep their higher precedence.
- `DEFUZE_CLIENT_PROVIDER`, `DEFUZE_CLIENT_MODEL`, `DEFUZE_CLIENT_BASE_URL`:
  ACP client-facing settings; default `deepseek`, `deepseek-chat`,
  `https://api.deepseek.com`. These describe the intercepted source, not the
  actual billed model. Native launcher catalogs still apply.

The host retains separate client and upstream configurations. It mounts the real
key only into the interceptor and injects a random per-run token into the Agent.
The target URL is `<KUMA_BASE_URL>/sdk/models/<family>`.

Before proxy readiness, an authenticated OPTIONS request checks the Chat
Completions permission gate. It requires HTTP 200, POST in Allow, and JSON metadata
with name `Sdk Agent Model` and `application/json` in `parses`. Redirects and
environment proxies are disabled; responses and timing are bounded. Permission
is checked afresh per container and never via a paid generation request. This
does not certify the selected model's modalities or other protocol endpoints.

Supported source protocols are Chat, thinking Chat, Responses, Anthropic Messages,
and their existing token-counting adapters. Native wire conversion, streaming,
credential validation and redacted evidence remain owned by the common proxy.
Unsupported protocols fail before forwarding. Separate-target ACP observe mode
and native `/models` metadata forwarding are rejected explicitly.

`target.py` adds one fresh Idempotency-Key to each prepared outbound request.
Transport reuse of that request retains its header. Independent Agent retries
have new keys; this is not a claim of cross-request billing deduplication. No
generation retry policy is added. Server-side idempotency semantics require
separate verification.

## OpenClaw acceptance limitation

The initial real OpenClaw acceptance reached the gateway with valid credentials,
but the server returned HTTP 400, `Sensitive data cannot be uploaded.` Offline
reproduction with the local Backend scanner located `named_credential_assignment`
in the `secrets` tool's function description. The interceptor preserves that tool
definition and the server rejection. No tool removal, prompt rewriting or privacy
filter bypass is applied. A server-side assessment of that description is needed
before this OpenClaw configuration can be claimed as accepted end to end.

The explicit smoke script `scripts/validate_defuze_openclaw.py` reads `.env` over
inherited process credentials for its own run. Normal CLI dotenv precedence is
unchanged. The script records the actual model, response, run status and trace
paths, and fails unless the Agent returns the requested tool-task marker.
