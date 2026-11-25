# Kimi Code native ACP integration

Builds the pinned Node monorepo with its frozen pnpm lockfile and native CLI build,
including the Web assets required by that build. Starts `node dist/main.mjs acp`.
The runtime launcher writes native provider/model configuration from
`ABB_AGENT_MODEL_*`; prompt templates and tool implementations remain upstream.
A conservative 32768-token context budget is configured for this greeting deployment.

Run in Docker Linux containers on Windows, macOS or Linux:
`python -m agentbench evaluate kimi-code --sdk native --case-file resources/agents/149-kimi-code/smoke-case.json --cases 1 --max-steps 1 --no-view -y`
