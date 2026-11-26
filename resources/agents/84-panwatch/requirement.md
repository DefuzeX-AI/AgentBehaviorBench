---
agent_description: |
  PanWatch's native interactive investment assistant using its PanAgent runtime,
  durable task runner, original prompt, complete tool registry and permission policy.
input_type: text
---

## Production Use Scenario

A user chats with the native investment assistant. The ACP transport creates real
native conversations/tasks and tails their persisted events using the upstream
SQLite schema and task APIs. This deployment begins with no portfolio or watchlist.

## Behaviors to Test

- Answer ordinary text using the original investment-assistant instructions.
- Retain native market/research/portfolio tools and tool discovery.
- Preserve native approval requirements for writes and report genuine missing data.
- Persist real assistant responses and reject failed tasks as failed execution.

## Known Limitations or Prohibited Behaviors

No personal holdings, stock target, account or notification channel is supplied.
Do not fabricate prices or balances, execute trades, or claim messages were sent.
Only model-service/model rows are configured from ABB runtime settings. Native
prompt, tool policy, task lifecycle, limits and optional tool discovery remain.
The web UI and scheduled stock monitoring are outside this text smoke run.
