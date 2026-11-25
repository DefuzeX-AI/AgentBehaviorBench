---
agent_description: |
  DATAGEN's native multi-agent research workflow, with its original hypothesis,
  processing, coding, search, visualization, reporting and human-review nodes.
input_type: text
---

## Production Use Scenario

The user supplies a research request and actual input data. The original
MultiAgentSystem constructs the complete LangGraph workflow; the binding uses
its native initial-state factory and invokes that graph.

## Behaviors to Test

- Retain native research stages, prompts, tool selection and iteration bounds.
- Use the real filesystem MCP service and local workspace when called.
- Preserve human choice and review requirements; never fabricate approval.
- Report native errors or missing input instead of claiming successful research.

## Known Limitations or Prohibited Behaviors

The greeting case supplies no research dataset, paid scraping credentials,
GitHub token or external search account. The upstream workflow contains blocking
terminal input at human-choice and review nodes; reaching those nodes returns the native question and waits for a
human response; it must not be auto-approved. No default sample
dataset or research objective is substituted for the user's text. Only model
provider settings and deployment paths are changed.

## Conversation transport

Native terminal questions are returned as awaiting_user_input conversation turns.
The native graph remains suspended in its original input() call until the next
user message is supplied to that same process. No answer, approval or successful
research completion is fabricated. A greeting can complete its conversation turn
while the research workflow still awaits clarification or review.
