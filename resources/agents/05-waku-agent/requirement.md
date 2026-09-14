# Waku Agent requirements

- Supply model-interception credentials for the declared OpenAI Chat Completions
  route. The container receives only the temporary `OPENAI_API_KEY` selected by
  ABB. The configured deployment model is `gpt-4.1-mini` for both Waku's main
  loop and its native retrieval/consolidation decisions.
- Permit HTTPS GET only to `html.duckduckgo.com` if Cases exercise native web
  search. The free endpoint may reject automation; Waku must surface that native
  failure and must not fabricate results. Tavily is disabled and has no route or
  credential in this deployment.
- Keep one adapter/native Waku instance per Case and a new private home per Case
  attempt. Reuse that instance for the Case's Inputs so Waku, rather than ABB,
  owns conversation and memory. Close it after the Case; never reuse its SQLite
  store, outbox, calendar, skills, traces, or generated files across Cases.
- Treat `send_message` as a Case-local draft and `create_event` as a local Waku
  record. Apple Calendar, Google Calendar, GitHub, Telegram, WhatsApp, Discord,
  MCP, experimental delegation, shell/browser execution, and remote publishing
  remain unavailable.
- Before promotion from `adapting`, build the pinned image, run a real `observe`,
  execute at least one multi-Input Case that demonstrates native history without
  ABB replay, inspect model/tool traces and isolation, and complete the official
  certification path. Offline fixtures do not establish those results.

Onboarding did not use a provider key, call a model, access DuckDuckGo, generate
Cases, request a Judge report, or run a benchmark.
