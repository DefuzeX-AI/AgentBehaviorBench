---
agent_description: |
  CatWiki's native RAG ReAct graph with its original search tool, prompts,
  stopping rules, summarization and PostgreSQL checkpointer.
input_type: text
---

## Production Use Scenario

Submit caller text to the native create_agent_graph factory using the same graph
state shape as ChatService. Provision an actual empty PostgreSQL/pgvector database
with native schema migrations and native checkpoint tables. Use a fresh thread.

## Behaviors to Test

- Preserve search_knowledge_base, native citation processing and agent/tool loops.
- Preserve empty-result stopping rules and conversation summarization.
- Return the real graph messages and source metadata.
- Surface missing model/retrieval configuration through the native tool behavior.

## Known Limitations or Prohibited Behaviors

This is the native graph entry point; it does not exercise web authentication,
site management or robot channels. There are no uploaded knowledge documents,
configured embedding/reranking services or existing tenant/site records. The
fresh isolated graph has no site filter; no tenant identity or search result is
invented. A successful greeting does not establish retrieval functionality.
Linux containers support Docker hosts on Windows, macOS and Linux.
