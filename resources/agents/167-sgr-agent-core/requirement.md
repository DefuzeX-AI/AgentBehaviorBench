---
agent_description: |
  SGR Agent Core's shipped SGR File Agent preset, served by its native sgracp
  command with the original prompt and read-only filesystem tools.
input_type: text
---

## Production Use Scenario

An ACP client asks the native file assistant to locate, read and analyze actual
files. This integration selects the upstream examples/sgr_file_agent preset and
preserves that preset's clarification, final-answer and filesystem tools.

## Behaviors to Test

- Answer through the original ToolCallingAgent loop and native ACP bridge.
- Preserve directory listing, file reading, content search and file-finding tools.
- Preserve native clarification and iteration limits and report native failures.

## Known Limitations or Prohibited Behaviors

No user documents are supplied to the empty workspace. Do not invent file
contents or claim successful searches without tool evidence. This is the shipped
file-agent preset, not the separate web-research preset. No tool, prompt or
native gate is replaced. The deployment avoids duplicate registration of the five
filesystem tools already supplied by SGRFileAgent, retaining those tools plus
clarification and final answer. When ABB selects DeepSeek, the native LLM
configuration disables thinking mode so its required tool choice is supported.
