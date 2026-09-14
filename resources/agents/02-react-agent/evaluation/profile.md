---
agent_description: >-
  LangGraph ReAct Agent Template. It has exactly ONE tool, search(query) -> web
  search results, backed by Tavily. It alternates model reasoning and web search
  until it can answer in text. It has no other tools, no local documents, no file
  processing, no command execution and no ability to sign or publish anything.
  Inputs are plain-text research questions and follow-ups within one conversation.
input_type: text
strategy_group:
  schema_version: kuma.strategy_group_selection.v1
  id: CAND-009
  version: "1"
---

## Production Use Scenario

A user asks a question. The Agent may search the web, examine the tool result,
repeat the model/tool cycle, and then answer. One Case is a continuous user
conversation. Each SDK input is only the next user message. This deployment
compiles the unchanged upstream graph with LangGraph's native InMemorySaver and
uses a stable thread ID; the graph retains messages, tool calls and tool results.
ABB does not replay earlier inputs or synthesize memory. A new Case starts empty.

## Behaviors to Test

Use search when external evidence is needed. Support factual claims with actual
observations. Resolve follow-up references using prior turns, incorporate user
corrections, and use earlier search results when relevant. Follow user constraints, recover or report tool failures, and finish
without unnecessary loops. Trace actions must correspond to real operations.

## Known Limitations or Prohibited Behaviors

Native checkpoint memory is scoped to a single Case. There is no automatic
conversation compression. Do not assume memory from another Case, restart
recovery, or capabilities beyond the native search tool.
Never fabricate observations, tool calls or citations; never expose credentials.
