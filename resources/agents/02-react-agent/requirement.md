---
agent_description: |
  The React Agent is a custom Reasoning and Action (ReAct) AI assistant implemented using the LangGraph framework. It utilizes a chat language model (default: Anthropic Claude Sonnet) with integrated tool-calling abilities. The agent cycles between reasoning steps invoking the chat model and executing external tools, such as web search using Tavily, to answer user queries. The agent maintains conversational messages as its core input state, supports tool invocation management, and iteratively produces responses until a final answer. This agent is designed as a flexible, minimal ReAct implementation demonstrating a reasoning and action loop within LangGraph.
input_type: text
strategy_group:
  schema_version: kuma.strategy_group_selection.v1
  id: basic-safety-general
  version: "1"
---

## Production Use Scenario

This agent is suitable for deployment as a conversational AI assistant that requires reasoning capabilities combined with tool integration in workflows such as information retrieval and web search. It can handle multi-turn dialogue where the model dynamically decides on invoking tools and processing their outputs to produce final answers. The LangGraph-based architecture allows flexible extension with additional tools and custom reasoning strategies.

It is intended for use cases requiring interactive, step-wise reasoning and tool execution, such as question answering augmented with live web searches or other APIs, where both model-generated text and structured tool call interactions are needed.


## Behaviors to Test

- Correctness of conversational state handling, including proper accumulation and merging of message sequences.
- Ability to invoke the configured language model (default: Anthropic Claude) and format system prompts dynamically with context such as system time.
- Proper recognition and execution of tool calls within model responses, including integration with the Tavily web search tool.
- Looping logic correctness where the agent repeatedly cycles between reasoning and tool execution nodes until a final response is produced or a step limit is reached.
- Handling last step edge cases where tool calls remain unresolved, returning a polite failure message.
- Input acceptance of raw text prompts transformed into message sequences by the LangGraph runtime.
- Stability and error handling in asynchronous model invocation and tool execution.


## Known Limitations or Prohibited Behaviors

- The agent currently processes inputs as complex message sequences internally but the BBA SDK integration requires a flat text input. The mapping between these formats relies on native LangGraph adapters, and no separate structured input schema is exposed or supported at the SDK boundary.
- The default model is tightly coupled to Anthropic Claude; while other providers like OpenAI can be configured, this has not been exhaustively tested.
- Toolset is minimal and example-only (e.g., Tavily web search), and does not cover robust or domain-specific tools out-of-the-box.
- The agent runs in a synchronous reasoning and action loop without advanced memory or multiturn management beyond message history.
- Behavior when the model repeatedly requests tool calls beyond configured step limits results in a fallback polite response but no graceful recovery.
- No native voice, GUI, or embodied simulation capabilities are present; this agent is purely text-based.
- Requires environment configuration for API keys (e.g., TAVILY_API_KEY, ANTHROPIC_API_KEY) managed externally; keys are not embedded or managed internally.
- Network requests for model and tool APIs depend on correct proxy and credential setup outside the agent boundary.
- There is no support for multi-input fields or complex structured inputs at the SDK interface; such needs must be met by augmenting the native graph or adapter separately.

