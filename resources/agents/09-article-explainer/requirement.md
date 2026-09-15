---
agent_description: >-
  Article Explainer is the original LangGraph swarm with five specialists:
  developer, summarizer, explainer, analogy_creator and vulnerability_expert.
  Each Input must be text containing the relevant article excerpt and its current
  question. Native handoff tools coordinate explanation, summaries, analogies,
  code examples and methodological critique. The full native state, including
  messages and active_agent, is returned. This text entrypoint has no web search,
  file upload or cross-Input conversation persistence.
input_type: text
strategy_group:
  schema_version: kuma.strategy_group_selection.v1
  id: CAND-002
  version: "1"
---

## Production Use Scenario

A reader supplies a complete technical excerpt and asks for explanation,
summarization, analogy, illustrative code or critique. The unchanged compiled
swarm chooses among its five native specialists and handoff tools. This deployment
calls the public graph directly, rather than reconstructing Streamlit UI state.

## Behaviors to Test

Ground statements in the supplied excerpt, distinguish analogy from literal
claims, explain uncertainty, and use relevant specialist handoffs without losing
the current request. Preserve the complete native result and identify the final
assistant message separately from internal handoff messages.

## Known Limitations or Prohibited Behaviors

Every Input must contain the source text needed to answer. No prior article,
PDF upload, native Streamlit conversation, web retrieval, code execution or
filesystem editing is available through this selected text entrypoint. The
upstream graph is compiled without a checkpointer; no history accumulator or
memory system is added. Do not invent source content, external tool results,
citations, executed code or prior conversations. Model credentials are private.
