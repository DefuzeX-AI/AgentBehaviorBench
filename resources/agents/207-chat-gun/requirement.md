---
agent_description: "Chat-Gun native MCP agent"
input_type: text
---

# Chat-Gun native MCP agent

This deployment runs the native LangGraph JS server, PostgreSQL migrations, Redis and BFF. A locally configured service API key is authenticated by the native BFF; graph calls retain production execution-context validation, database task admission, interaction governance and tool authorization. No development execution-context switch, fake task record or fabricated tool approval is used.

Text messages enter the upstream `mcp_agent` through the BFF's thread/run API. Native prompts, tool discovery and graph routing remain unchanged. Tool execution depends on the original permissions and available MCP service configuration. No external search credential, business data, consumer account or storefront is invented. Requests for approval or missing external prerequisites remain visible failures or interruptions.

The isolated services listen locally in the container. The Docker build uses Linux dependencies suitable for Docker hosts on Windows, macOS and Linux.
