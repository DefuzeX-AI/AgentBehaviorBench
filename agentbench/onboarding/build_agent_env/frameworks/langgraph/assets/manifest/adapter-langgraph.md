Apply these instructions ONLY when source evidence establishes a compatible
LangGraph execution interface and the selected framework is langgraph. Installing
langchain as a dependency alone does not prove the Agent runs through LangGraph.

The program sets [adapter] type="langgraph", mode="in_process" for this integration.
If an existing JSON graph descriptor is supplied, extract config as its path
relative to agent/ and graph_id as its actual JSON graph key. A Python module
such as graph.py is NOT a JSON descriptor.
If the native LangGraph is built through a source-confirmed Python factory or
public workflow without a JSON descriptor, set config=null and graph_id=null.
The outer binding is the direct loader entrypoint and must call the real native
factory/workflow. No upstream descriptor or guessed graph key is needed.
Always declare binding from plan.bindings, as "filename.py:factory" relative to
outer bindings/. A compatible native graph still needs a forwarding factory.
Do not invent a graph configuration or replace a
different framework's native lifecycle with a demonstration LangGraph wrapper.

input_key/output_key are optional. Mapping inputs pass through unchanged; input_key
wraps scalar text only. Omit output_key when returning complete state. adapter.context
is LangGraph invocation context, NOT RunnableConfig.configurable. Do not pretend
configurable defaults can be overridden through context. The program owns context
and replay_safe policy; do not return either in model facts. Do not add history or
memory scaffolding.
