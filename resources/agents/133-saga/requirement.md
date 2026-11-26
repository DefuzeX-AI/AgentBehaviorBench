---
agent_description: |
  SAGA native story-project bootstrap workflow.
input_type: text
---

## Production Use Scenario

Accept a story premise through the official bootstrap entrypoint and return the
validated native project configuration as a review candidate. The greeting smoke
case uses its supplied text as a minimal premise. No novel is generated or approved.

## Behaviors to Test

Preserve native metadata prompts, schema validation and review-required output.
Report failures rather than inventing configuration or completed chapters.

## Limitations

This deployment verifies bootstrap mode only. Full manuscript generation requires
Neo4j/APOC, an embedding service and the native statistical language pipeline.
