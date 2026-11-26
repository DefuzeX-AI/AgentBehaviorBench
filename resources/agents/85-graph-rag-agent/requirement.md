---
agent_description: |
  Graph RAG Agent's native default NaiveRagAgent using its original search tool,
  graph, prompt chain, cache lifecycle and ask_with_trace execution.
input_type: text
---

## Production Use Scenario

A user asks the default knowledge assistant a text question. A real disposable
Neo4j database starts empty; the native cache encoder is packaged with the image.
Native model selection is routed through ABB replacement without editing source.

## Behaviors to Test

- Answer ordinary text through the upstream graph and preserve tool decisions.
- Retain native search and cache behavior, including errors from missing data.
- Report empty or unavailable retrieval evidence without fabricating documents.

## Known Limitations or Prohibited Behaviors

No populated knowledge graph or indexed documents are supplied. The upstream
OpenAI embedding client remains intact, but this deployment only configures chat
replacement: an actual remote embedding request needs a separate usable embedding
service and is not claimed as available. The native sentence-transformer cache
encoder supports CPU execution. No training pipeline or GPU model load is enabled.
