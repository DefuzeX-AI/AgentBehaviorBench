"""Cross-terrain multi-hop relay task for heterogeneous delivery."""

from typing import Any, TypedDict

from app.modules.agents.definition import AgentDefinition
from app.modules.agents.graphs import import_langgraph
from app.modules.agents.tasks.common import as_list, base_metadata, command


class CrossTerrainRelayState(TypedDict, total=False):
    """State for decomposing a delivery into terrain-specific relay legs."""

    cargo: dict[str, Any]
    terrain_segments: list[dict[str, Any]]
    available_assets: dict[str, list[str]]
    relay_plan: list[dict[str, Any]]
    synchronization_plan: list[dict[str, Any]]
    commands: list[dict[str, Any]]
    evaluation_metrics: dict[str, str]
    metadata: dict[str, Any]


TERRAIN_TO_ASSET = {
    "road": "ugv",
    "plain": "ugv",
    "water": "usv",
    "river": "usv",
    "mountain": "uav",
    "vertical": "uav",
    "no_road": "uav",
}


def build_graph():
    """Build the cross-terrain relay graph."""

    start, end, state_graph = import_langgraph()

    def assign_assets(state: CrossTerrainRelayState) -> dict[str, Any]:
        segments = as_list(state.get("terrain_segments")) or [{"terrain": "road", "name": "default_leg"}]
        available = state.get("available_assets", {})
        relay_plan = []
        for index, segment in enumerate(segments):
            category = TERRAIN_TO_ASSET.get(segment.get("terrain"), "ugv")
            asset_pool = available.get(category) or [category]
            relay_plan.append(
                {
                    "order": index + 1,
                    "segment": segment,
                    "asset_category": category,
                    "assigned_asset": asset_pool[0],
                }
            )
        return {"relay_plan": relay_plan}

    def synchronize_handoffs(state: CrossTerrainRelayState) -> dict[str, Any]:
        plan = state.get("relay_plan", [])
        sync = [
            {
                "from": plan[index]["assigned_asset"],
                "to": plan[index + 1]["assigned_asset"],
                "handoff_after_order": plan[index]["order"],
            }
            for index in range(max(len(plan) - 1, 0))
        ]
        return {"synchronization_plan": sync}

    def generate_commands(state: CrossTerrainRelayState) -> dict[str, Any]:
        commands = [
            command(
                "relayTransport",
                item["assigned_asset"],
                {"cargo": state.get("cargo", {}), "relay_step": item},
            )
            for item in state.get("relay_plan", [])
        ]
        return {
            "commands": commands,
            "evaluation_metrics": {
                "Relay SR": "success rate of physical handoff between nodes",
                "Task Allocation Validity": "whether each terrain segment matches asset capability",
                "Synchronization Delay": "idle waiting caused by relay coordination",
            },
            "metadata": base_metadata(state, "cross_terrain_relay"),
        }

    graph = state_graph(CrossTerrainRelayState)
    graph.add_node("assign_assets", assign_assets)
    graph.add_node("synchronize_handoffs", synchronize_handoffs)
    graph.add_node("generate_commands", generate_commands)
    graph.add_edge(start, "assign_assets")
    graph.add_edge("assign_assets", "synchronize_handoffs")
    graph.add_edge("synchronize_handoffs", "generate_commands")
    graph.add_edge("generate_commands", end)
    return graph.compile()


AGENT_DEFINITION = AgentDefinition(
    name="cross_terrain_relay",
    description="Assign heterogeneous assets for cross-terrain multi-hop cargo delivery.",
    builder=build_graph,
)
