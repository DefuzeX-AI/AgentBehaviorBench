# OpenBot native LangGraph integration

Uses `agent-langgraph-agui/src/main.py:graph` through the upstream
`ToolAwareAgent.run` AG-UI entrypoint. Native answer/tool nodes, per-run memory,
message handling and errors are retained. The AG-UI caller supplies role messages
and tool grants; none have been provided for this standalone greeting. No default
builtin tools are removed: tools are exclusively offered by the calling deployment.
This is a backend smoke test, not the complete organization application.

The native source model defaults to gpt-4o-mini. ABB replace selects the actual
shared provider/model. No real model key is copied into this unit.

Run with Docker Linux containers on Windows, macOS or Linux:
`python -m agentbench evaluate openbot --sdk native --case-file resources/agents/74-openbot/smoke-case.json --cases 1 --max-steps 1 --no-view -y`
