# ReAct Agent

Original LangGraph ReAct template from https://github.com/langchain-ai/react-agent,
revision 9bbd82d84905acc37f527b1f372dae841016f3b4. Upstream source is unchanged.

Accept a natural-language user request, alternate model/tool execution as needed,
and return a final answer supported by actual observations. The native tool is
Tavily search. Do not fabricate tool results, successful calls, or citations.
Handle missing information and errors truthfully; do not disclose credentials.

ABB accepts text, {"message": "..."}, or {"messages": [...]} native conversation
history. Only one input shape is accepted at a time. The final assistant text is
submitted to the SDK; complete messages remain in raw output and framework trace.

This initial Docker configuration is one-shot: separate SDK Inputs do not share
memory automatically. Explicit history may be supplied through messages. Persistent
multi-turn sessions and cross-turn trace identity require a subsequent runtime
session design; do not claim that a stable thread_id alone provides memory.

Status: adapting. Real model/search certification has not been completed.
