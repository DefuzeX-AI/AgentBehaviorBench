# TerminaI Agent Slot (#113)

- **Agent Name**: TerminaI
- **Agent ID**: terminai
- **Slot**: #113 (`resources/agents/113-terminai`)
- **Upstream Repository**: https://github.com/Prof-Harita/terminaI
- **Pinned Commit**: 4b816c7acc5a89afb692d512c046cdc61bf6186b (Apache-2.0)
- **Framework**: Native ACP (`bundle/gemini.js --experimental-acp`)
- **Transport**: Stdio ACP relay via `bootstrap/launch.py`
- **Model**: deepseek/deepseek-chat (https://api.deepseek.com)

## Architecture

TerminaI is an autonomous AI developer agent built on TypeScript / Node.js. It natively supports ACP (Agent Client Protocol) over stdio via the `--experimental-acp` CLI flag:
1. Docker build builds the package bundle `bundle/gemini.js`.
2. `bootstrap/launch.py` acts as an unprivileged supervisor that translates ABB dynamic runtime environment variables (`ABB_AGENT_MODEL_*`) into `~/.terminai/settings.json` configuring `llm.provider = "openai_compatible"`.
3. ABB Harness communicates with TerminaI via standard ACP v1 JSON-RPC over stdio.
