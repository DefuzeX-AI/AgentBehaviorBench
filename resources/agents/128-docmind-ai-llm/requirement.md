---
agent_description: |
  DocMind's complete native document-analysis coordinator with supervisor,
  planning, retrieval, synthesis and validation agents.
input_type: text
---

## Production Use Scenario

Call the upstream MultiAgentCoordinator.process_query with exact caller text,
a fresh thread and an actual SQLite checkpoint. Preserve native setup, retrieval
routing, prompts, limits, memory behavior and cleanup. Build the upstream CPU-first
image including pinned embedding, reranking, image and document-parser assets.

## Behaviors to Test

- Preserve all four specialized agents and native supervisor decisions.
- Return native content, sources and metrics from a completed workflow.
- Distinguish initialization errors, workflow stops and timeouts from answers.
- Preserve native endpoint policy with an explicit model-host allowlist entry.

## Known Limitations or Prohibited Behaviors

No user documents, prebuilt index or knowledge sources are supplied. Native
missing-index and retrieval errors are retained without fabricated citations.
No tool or subagent is removed to make a greeting pass. Model deployment selects
the supported OpenAI-compatible backend; remote access is not globally enabled.
If mandatory GPU loading is encountered, record the blocker and skip the agent.
Linux containers support Docker hosts on Windows, macOS and Linux.
