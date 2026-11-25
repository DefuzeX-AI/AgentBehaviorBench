---
agent_description: |
  SearChat's native SearchChat agent, including its intent-analysis LangGraph,
  query rewriting, real search adapter and native final-answer generation.
input_type: text
---

## Production Use Scenario

A caller sends text to the upstream SearchChat implementation. It decides
whether search is required, executes its original graph and streams the native
answer. The outer ACP layer transports that input and output.

## Behaviors to Test

- Preserve native search-intent decisions, query rewriting and final prompts.
- Return the real native event stream, replies and failures.
- Never invent search results or claim unobserved sources.

## Known Limitations or Prohibited Behaviors

The default SearXNG adapter is retained, but no SearXNG deployment or paid search
credential is provided. A greeting that does not invoke search can succeed;
that does not establish working web search. No search function is replaced by a
stub. Only a provider entry for the configured model endpoint is added to the
native runtime model configuration; native source and prompts stay unchanged.
