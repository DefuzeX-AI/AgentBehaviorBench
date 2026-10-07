"""Timed wide-area space-ground cooperative observation task."""

from typing import Any, TypedDict

from app.modules.agents.definition import AgentDefinition
from app.modules.agents.graphs import import_langgraph
from app.modules.agents.tasks.common import as_list, base_metadata, command


class SatelliteObservationState(TypedDict, total=False):
    """State for satellite constellation observation scheduling."""

    target_area: str
    time_window: dict[str, Any]
    satellites: list[dict[str, Any]]
    observation_plan: list[dict[str, Any]]
    downlink_plan: list[dict[str, Any]]
    commands: list[dict[str, Any]]
    evaluation_metrics: dict[str, str]
    metadata: dict[str, Any]


def build_graph():
    """Build the satellite observation scheduling graph."""

    start, end, state_graph = import_langgraph()

    def schedule_observation(state: SatelliteObservationState) -> dict[str, Any]:
        satellites = as_list(state.get("satellites")) or [
            {"id": "optical_sat", "payload": "optical"},
            {"id": "sar_sat", "payload": "SAR"},
        ]
        plan = [
            {
                "satellite": sat,
                "target_area": state.get("target_area", "unknown_area"),
                "time_window": state.get("time_window", {}),
                "mode": "best_available_pass",
            }
            for sat in satellites
        ]
        return {"observation_plan": plan}

    def plan_downlink(state: SatelliteObservationState) -> dict[str, Any]:
        return {
            "downlink_plan": [
                {
                    "satellite": item["satellite"]["id"],
                    "data_type": item["satellite"].get("payload", "unknown"),
                    "priority": "high",
                }
                for item in state.get("observation_plan", [])
            ]
        }

    def generate_commands(state: SatelliteObservationState) -> dict[str, Any]:
        commands = [
            command(
                "satelliteObserveAndDownlink",
                item["satellite"],
                {"observation": state.get("observation_plan", []), "downlink": item},
            )
            for item in state.get("downlink_plan", [])
        ]
        return {
            "commands": commands,
            "evaluation_metrics": {
                "Effective Coverage Ratio": "valid no-cloud/high-SNR covered area ratio",
                "Data Downlink Latency": "end-to-end time from imaging to ground receipt",
            },
            "metadata": base_metadata(state, "satellite_observation"),
        }

    graph = state_graph(SatelliteObservationState)
    graph.add_node("schedule_observation", schedule_observation)
    graph.add_node("plan_downlink", plan_downlink)
    graph.add_node("generate_commands", generate_commands)
    graph.add_edge(start, "schedule_observation")
    graph.add_edge("schedule_observation", "plan_downlink")
    graph.add_edge("plan_downlink", "generate_commands")
    graph.add_edge("generate_commands", end)
    return graph.compile()


AGENT_DEFINITION = AgentDefinition(
    name="satellite_observation",
    description="Schedule satellite observation and data downlink inside a time window.",
    builder=build_graph,
)
