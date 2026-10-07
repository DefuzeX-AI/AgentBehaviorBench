"""LangGraph task for UAV route planning and command dispatch."""

from typing import Any

from app.modules.agents.definition import AgentDefinition
from app.modules.agents.graphs import import_langgraph
from app.modules.agents.state import UavRoutePlanState
from app.modules.ai.service import analysis, parse_model_json, read_prompt
from app.modules.realtime.manager import realtime_manager


def build_graph():
    """Build the UAV route planning workflow graph."""

    start, end, state_graph = import_langgraph()

    def build_messages_node(state: UavRoutePlanState) -> dict[str, Any]:
        """Create the multimodal message payload expected by the AI service."""

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": read_prompt("2")},
                    {
                        "type": "image_url",
                        "image_url": {"url": state["map_base64"], "detail": "auto"},
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": state["image_base64"], "detail": "auto"},
                    },
                ],
            }
        ]
        return {"messages": messages}

    async def call_ai_node(state: UavRoutePlanState) -> dict[str, Any]:
        """Ask the model to produce the next route-planning action."""

        response = await analysis(state["messages"])
        return {"ai_response": response}

    def parse_plan_node(state: UavRoutePlanState) -> dict[str, Any]:
        """Parse and validate the model's route plan JSON."""

        plan = parse_model_json(state["ai_response"])
        return {
            "route_plan": plan,
            "metadata": {
                **state.get("metadata", {}),
                "graph": "uav_route_plan",
                "framework": "langgraph",
            },
        }

    async def dispatch_command_node(state: UavRoutePlanState) -> dict[str, Any]:
        """Send targetpoint commands to LJ-ENGINE when the plan says continue."""

        plan = state["route_plan"]
        if plan.get("status") != "continue" or not plan.get("offset"):
            return {}
        offset = plan["offset"]
        command = {
            "commandType": "sendInstruction",
            "instructionType": "targetpoint",
            "location": {"x": offset[0], "y": offset[1], "z": 0.0},
            "command": {"speed": 25.0},
        }
        await realtime_manager.send_by_user_type({"type": "COMMAND", "data": command}, "LJ-ENGINE")
        return {"dispatched_command": command}

    graph = state_graph(UavRoutePlanState)
    graph.add_node("build_messages", build_messages_node)
    graph.add_node("call_ai", call_ai_node)
    graph.add_node("parse_plan", parse_plan_node)
    graph.add_node("dispatch_command", dispatch_command_node)
    graph.add_edge(start, "build_messages")
    graph.add_edge("build_messages", "call_ai")
    graph.add_edge("call_ai", "parse_plan")
    graph.add_edge("parse_plan", "dispatch_command")
    graph.add_edge("dispatch_command", end)
    return graph.compile()


AGENT_DEFINITION = AgentDefinition(
    name="uav_route_plan",
    description="Plan UAV route from current image and map image, then dispatch engine commands.",
    builder=build_graph,
)
