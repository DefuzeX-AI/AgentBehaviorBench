---
agent_description: |
  Optimizer's native Fund cockpit Ask agent: a read-only DeepAgent with original
  database-reading tools, filesystem permissions, helper agent and turn runner.
input_type: text
---

## Production Use Scenario

Use the upstream build_ask_agent and run_ask_turn paths with an actual isolated
PostgreSQL database, native portopt-db migrations and native LangGraph persistence.
Use the native fund-wide scope with no selected portfolio. Stage the upstream
source and documentation through its own read-only backend constructor.

## Behaviors to Test

- Preserve native system prompts, read-only tool permissions and bounded helper.
- Preserve native summarization, checkpoints and turn limits.
- Return the native answer and report errors or exhausted turns accurately.
- Ask for missing portfolio or market data without inventing holdings or prices.

## Known Limitations or Prohibited Behaviors

This entry point is the native Ask adviser, not the separate rebalance workflow.
The database has no seeded portfolios, mandates, market quotes or orders. No
broker connection or human approval is supplied. Model deployment selects the
native OpenAI provider; all other Ask behavior uses upstream defaults.
Linux containers support Docker hosts on Windows, macOS and Linux.
