---
agent_description: "Specifai native requirement chat"
input_type: text
---

# Specifai native requirement chat

The deployment runs the native Electron `chatWithAI` handler, including its original prompt, guardrails, summarization, LangGraph agent, requirement tools and MCP connection discovery. A real Electron process, private store, hidden BrowserWindow and WebContents carry the native event stream. The transport returns the completed native graph result and never fabricates tool outcomes.

The smoke input enters the BRD conversation with empty project and requirement fields. No project description, business requirement, linked document or external MCP connection is invented. Requirement update tools retain their original suggestion behavior; the adapter does not approve or apply document changes. The greeting only verifies this native conversation entrypoint, not a populated product-management workflow or GUI editing.

The native configurable OpenRouter-compatible provider consumes ABB's model, endpoint and credential settings. The Docker image builds the full Electron backend and uses an isolated virtual X display on Linux Docker hosts, including Docker Desktop on Windows and macOS.
