---
agent_description: |
  Jar3d's original Chainlit requirements-gathering conversation and subsequent
  native meta-agent team workflow, served through the real websocket UI protocol.
input_type: text
---

## Production Use Scenario

The native application first introduces itself, then gathers the user's task
requirements. Only a real user `/end` message starts its original MetaAgent,
Serper search/shopping, scraper, RAG and reporter workflow. This greeting test
uses `你好` and does not invent requirements or submit `/end` on the user's behalf.

## Behaviors to Test

- Execute native chat initialization and the actual on-message callback.
- Preserve prompts, team construction, history and the `/end` admission stage.
- Return the response to the supplied input, excluding the startup greeting.
- Surface native error messages as execution failures.

## Known Limitations or Prohibited Behaviors

This greeting tests the native requirements conversation, not task completion by
the downstream team. No Serper, Anthropic, Neo4j or LangSmith account was supplied.
These tools remain native and may report missing credentials if invoked. No
fake search results, documents or task requirements are supplied. Only the
OpenAI key is injected; ABB intercepts the native model requests in replace mode.
The Linux image supports Docker hosts on Windows, macOS and Linux.
