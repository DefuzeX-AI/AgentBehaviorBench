"""LangGraph task for UAV fire reconnaissance."""

from typing import Any

from app.modules.agents.definition import AgentDefinition
from app.modules.agents.graphs import import_langgraph
from app.modules.agents.state import UavReconState
from app.modules.ai.service import analysis, parse_model_json


def build_graph():
    """Build the UAV reconnaissance workflow graph."""

    start, end, state_graph = import_langgraph()

    async def call_ai_node(state: UavReconState) -> dict[str, Any]:
        """Send the uploaded UAV image to the AI analysis service."""

        response = await analysis({"type": "1", "imageBase64": state["image_base64"]})
        return {"ai_response": response}

    def parse_result_node(state: UavReconState) -> dict[str, Any]:
        """Parse model JSON and normalize `result` into a boolean."""

        parsed = parse_model_json(state["ai_response"])
        result = parsed.get("result")
        if isinstance(result, str):
            result = result.lower() == "true"
        return {
            "parsed_response": parsed,
            "result": bool(result),
            "metadata": {
                **state.get("metadata", {}),
                "graph": "uav_recon",
                "framework": "langgraph",
            },
        }

    graph = state_graph(UavReconState)
    graph.add_node("call_ai", call_ai_node)
    graph.add_node("parse_result", parse_result_node)
    graph.add_edge(start, "call_ai")
    graph.add_edge("call_ai", "parse_result")
    graph.add_edge("parse_result", end)
    return graph.compile()


AGENT_DEFINITION = AgentDefinition(
    name="uav_recon",
    description="Analyze a UAV image and return whether fire is detected.",
    builder=build_graph,
)
