"""Multi-agent cross-domain target search task."""

from typing import Any, TypedDict

from app.modules.agents.definition import AgentDefinition
from app.modules.agents.graphs import import_langgraph
from app.modules.agents.tasks.common import as_list, base_metadata, command


class CrossDomainTargetSearchState(TypedDict, total=False):
    """State for macro-to-micro heterogeneous target search."""

    target_description: str
    macro_assets: list[str]
    micro_assets: list[str]
    search_areas: list[str]
    priors: list[dict[str, Any]]
    handoff_plan: list[dict[str, Any]]
    commands: list[dict[str, Any]]
    evaluation_metrics: dict[str, str]
    metadata: dict[str, Any]


def build_graph():
    """Build the hierarchical cross-domain search graph."""

    start, end, state_graph = import_langgraph()

    def macro_scan(state: CrossDomainTargetSearchState) -> dict[str, Any]:
        macro_assets = as_list(state.get("macro_assets")) or ["uav"]
        areas = as_list(state.get("search_areas")) or ["wide_area"]
        priors = [
            {
                "source_asset": macro_assets[index % len(macro_assets)],
                "area": area,
                "target_hint": state.get("target_description", ""),
                "prior_coord": None,
            }
            for index, area in enumerate(areas)
        ]
        return {"priors": priors}

    def assign_micro_verification(state: CrossDomainTargetSearchState) -> dict[str, Any]:
        micro_assets = as_list(state.get("micro_assets")) or ["ugv", "robot_dog"]
        handoff = [
            {
                "prior": prior,
                "assigned_asset": micro_assets[index % len(micro_assets)],
                "action": "close_range_verify",
            }
            for index, prior in enumerate(state.get("priors", []))
        ]
        return {"handoff_plan": handoff}

    def generate_commands(state: CrossDomainTargetSearchState) -> dict[str, Any]:
        commands = [
            command(
                "macroMicroSearch",
                item["assigned_asset"],
                {"prior": item["prior"], "action": item["action"]},
            )
            for item in state.get("handoff_plan", [])
        ]
        return {
            "commands": commands,
            "evaluation_metrics": {
                "Search Time": "time reduction compared with blind single-agent search",
                "Communication Payload": "cross-domain data/token payload size",
                "FPR": "false positive rate of macro priors",
                "Miss Rate": "ratio of missed true targets",
            },
            "metadata": base_metadata(state, "cross_domain_target_search"),
        }

    graph = state_graph(CrossDomainTargetSearchState)
    graph.add_node("macro_scan", macro_scan)
    graph.add_node("assign_micro_verification", assign_micro_verification)
    graph.add_node("generate_commands", generate_commands)
    graph.add_edge(start, "macro_scan")
    graph.add_edge("macro_scan", "assign_micro_verification")
    graph.add_edge("assign_micro_verification", "generate_commands")
    graph.add_edge("generate_commands", end)
    return graph.compile()


AGENT_DEFINITION = AgentDefinition(
    name="cross_domain_target_search",
    description="Coordinate macro scan assets and micro verification assets for target search.",
    builder=build_graph,
)
