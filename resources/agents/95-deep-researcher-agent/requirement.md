---
agent_description: |
  NVIDIA Deep Researcher routes text queries through its native LangGraph intent classifier, shallow researcher and deep researcher. This integration invokes the complete NAT-owned workflow through the upstream WorkflowRunner. It uses the pinned MCP workflow's agent, prompt and tool settings, with model-client configuration adapted for ABB replacement inference. It returns the native terminal outcome rather than HTTP MCP jobs or ACP messages.
input_type: text
---

# NVIDIA Deep Researcher

## Production Use Scenario

Supply one nonempty text query, such as a greeting or a research question. Each input creates an independent native workflow and checkpoint conversation. The workflow classifies the query and chooses its native route; the binding does not force a research depth or replace the answer.

The returned object is the native `WorkflowSuccess` serialized as `{"status": "success", "result": "..."}`. Native `WorkflowFailure` outcomes and initialization errors raise an execution error. A completed greeting does not demonstrate successful external research or citation verification.

## Behaviors to Test

- Appropriate intent routing, including native replies to meta/conversational input.
- Research answers grounded in retrieved evidence when tools and credentials are available.
- Native shallow/deep research planning, source routing, writing and citation behavior.
- Accurate reporting of unavailable sources, missing credentials and failed research.

The unchanged source registry contains `web_search_tool` and `advanced_web_search_tool`, both backed by Tavily. Native agent-specific exclusions and planning limits remain intact. The stateless MCP workflow disables clarification and separate asynchronous deep-research jobs; this binding retains those workflow settings.

## Known Limitations or Prohibited Behaviors

Tavily search requires `TAVILY_API_KEY`. When absent, upstream still registers the tools but returns an explicit unavailable error on invocation; the binding neither supplies fake search results nor removes tools. The greeting smoke case requires no search key. External network access is restricted to the configured model and Tavily routes.

This deployment invokes the native workflow in process. It does not expose the MCP server, asynchronous job polling, a web frontend or ACP sessions. Checkpoints use native SQLite storage in the writable workspace; the MCP HTTP job server's shared PostgreSQL ledger is not started.

The default selected workflow uses remote inference, with no mandatory local GPU model loading. No optional local retrieval or GPU model service is provisioned. Native research prompts, tool implementations and workflow branches remain unchanged.
