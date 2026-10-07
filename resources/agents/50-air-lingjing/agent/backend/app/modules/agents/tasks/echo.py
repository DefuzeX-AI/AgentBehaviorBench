"""Minimal LangGraph task used as a template for future agents."""

from typing import Any

from app.modules.agents.definition import AgentDefinition
from app.modules.agents.graphs import import_langgraph
from app.modules.agents.state import AgentState


def build_graph():
    """Build a graph that copies `input` to `output`."""

    start, end, state_graph = import_langgraph()

    def echo_node(state: AgentState) -> dict[str, Any]:
        user_input = state.get("input", "")
        return {
            "output": user_input,
            "metadata": {
                **state.get("metadata", {}),
                "graph": "echo",
                "framework": "langgraph",
            },
        }

    graph = state_graph(AgentState)
    graph.add_node("echo", echo_node)
    graph.add_edge(start, "echo")
    graph.add_edge("echo", end)
    return graph.compile()


AGENT_DEFINITION = AgentDefinition(
    name="echo",
    description="Minimal LangGraph template that echoes input into output.",
    builder=build_graph,
)
