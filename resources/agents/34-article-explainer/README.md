# 37 Article Explainer

[duartecaldascardoso/article-explainer](https://github.com/duartecaldascardoso/article-explainer) at
`2cf067dc4b9158b03361c7b3e2544e067b75f1ae`, imported with `agentbench agent add` and configured with
`agent add -b --sdk kuma` (build model `glm-5.3-flash`).

## What is deployed

The upstream LangGraph swarm in `agent/explainer/graph.py`: five `create_react_agent` specialists (explainer,
summarizer, developer, analogy_creator, vulnerability_expert) joined by `langgraph_swarm.create_swarm(...,
default_active_agent="explainer")`. The only tools are the swarm handoff tools. Text in, text out: the article text
must be inside the message. The Streamlit page, its PDF upload and the Ollama fallback are not deployed.

## Changes around the upstream source

- `agent/abb-langgraph.json` is the only file added under `agent/`. Upstream has no `langgraph.json`; the descriptor
  points at the unchanged `./explainer/graph.py:app`. Without it `agent add -b` collects no Python source for this
  repository.
- `bindings/bridge.py` compiles the unchanged `agent_swarm` with LangGraph's `InMemorySaver`. Upstream's `app` has no
  checkpointer, so each Input restarted the conversation and the active agent, while the native Streamlit page keeps
  appending to one `messages` list. The ABB worker supplies a stable per-Case `thread_id`, so earlier turns and the
  active specialist persist within a Case and nothing persists across Cases. The generated binding had dropped this
  (ABB fixed the same issue in `20733d968`); without it a 3-step local smoke Case fails at the summary step.
- `requirement.md` is the generated profile, unchanged. Its Production Use Scenario is 1,230 characters; together
  with the execution-environment block that `evaluate --sdk kuma` now appends (d72c80ff) it stays under the 4,000
  character Case-generation limit.

## Validation

| Run | Model | Result |
|---|---|---|
| `evaluate --sdk kuma --cases 1` | `glm-5.3-flash` | 6-step Case (queue-policy article task with several handoffs to the summarizer): **execution 6/6, host accepted, official Judge `pass` (high)**, 1,135 s |
| `evaluate --sdk local --cases 1` | `glm-5.3-flash` | 3/3 steps executed; step 3 answered by the summarizer from the two earlier turns |

Known upstream behaviour: the model can emit two handoff tool calls in one message (for example
`transfer_to_summarizer` + `transfer_to_analogy_creator`). `langgraph_swarm` executes one, the other tool call has
no ToolMessage, and the next model call fails with `INVALID_CHAT_HISTORY`. This was seen once in an earlier run with
`glm-5.3-flash`; it is upstream graph behaviour and is not masked here.
