"""Constraint-aware physical boundary planning task."""

from typing import Any, TypedDict

from app.modules.agents.definition import AgentDefinition
from app.modules.agents.graphs import import_langgraph
from app.modules.agents.tasks.common import as_list, base_metadata, command


class ConstraintAwarePlanningState(TypedDict, total=False):
    """State for planning under energy, risk, and forbidden-zone constraints."""

    objective: str
    asset_type: str
    targets: list[dict[str, Any]]
    constraints: dict[str, Any]
    feasible_targets: list[dict[str, Any]]
    route_plan: list[dict[str, Any]]
    commands: list[dict[str, Any]]
    evaluation_metrics: dict[str, str]
    metadata: dict[str, Any]


def build_graph():
    """Build the constraint-aware planning graph."""

    start, end, state_graph = import_langgraph()

    def filter_feasible_targets(state: ConstraintAwarePlanningState) -> dict[str, Any]:
        constraints = state.get("constraints", {})
        max_risk = constraints.get("max_risk", 1.0)
        targets = as_list(state.get("targets")) or [{"id": "default_target", "risk": 0.0}]
        feasible = [target for target in targets if target.get("risk", 0.0) <= max_risk]
        return {"feasible_targets": feasible}

    def plan_route(state: ConstraintAwarePlanningState) -> dict[str, Any]:
        route = [
            {
                "order": index + 1,
                "target": target,
                "constraint_mode": "energy_risk_balanced",
            }
            for index, target in enumerate(state.get("feasible_targets", []))
        ]
        return {"route_plan": route}

    def generate_commands(state: ConstraintAwarePlanningState) -> dict[str, Any]:
        target_asset = state.get("asset_type") or "uav"
        return {
            "commands": [
                command(
                    "constraintAwareNavigate",
                    target_asset,
                    {"route_step": step, "constraints": state.get("constraints", {})},
                )
                for step in state.get("route_plan", [])
            ],
            "evaluation_metrics": {
                "Constraint Violation": "frequency of forbidden or infeasible actions",
                "Coverage Reward": "covered objective value under limited resources",
                "Energy Efficiency": "mission utility per energy consumed",
            },
            "metadata": base_metadata(state, "constraint_aware_planning"),
        }

    graph = state_graph(ConstraintAwarePlanningState)
    graph.add_node("filter_feasible_targets", filter_feasible_targets)
    graph.add_node("plan_route", plan_route)
    graph.add_node("generate_commands", generate_commands)
    graph.add_edge(start, "filter_feasible_targets")
    graph.add_edge("filter_feasible_targets", "plan_route")
    graph.add_edge("plan_route", "generate_commands")
    graph.add_edge("generate_commands", end)
    return graph.compile()


AGENT_DEFINITION = AgentDefinition(
    name="constraint_aware_planning",
    description="Plan routes under energy, risk, and physical boundary constraints.",
    builder=build_graph,
)
