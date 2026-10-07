"""Long-horizon semantic sequence planning task."""

from typing import Any, TypedDict

from app.modules.agents.definition import AgentDefinition
from app.modules.agents.graphs import import_langgraph
from app.modules.agents.tasks.common import as_list, base_metadata, command


class SemanticSequencePlanningState(TypedDict, total=False):
    """State for decomposing complex tasks into ordered subtasks."""

    mission: str
    asset_type: str
    subtasks: list[dict[str, Any]]
    execution_sequence: list[dict[str, Any]]
    commands: list[dict[str, Any]]
    evaluation_metrics: dict[str, str]
    metadata: dict[str, Any]


def build_graph():
    """Build the semantic sequence planning graph."""

    start, end, state_graph = import_langgraph()

    def decompose_mission(state: SemanticSequencePlanningState) -> dict[str, Any]:
        requested = as_list(state.get("subtasks"))
        subtasks = requested or [
            {"task": "takeoff_or_start", "order": 1},
            {"task": "navigate_to_work_area", "order": 2},
            {"task": "perform_observation_or_delivery", "order": 3},
            {"task": "return_or_shutdown", "order": 4},
        ]
        return {"subtasks": subtasks}

    def enforce_order(state: SemanticSequencePlanningState) -> dict[str, Any]:
        sequence = sorted(
            state.get("subtasks", []),
            key=lambda item: item.get("order", 0),
        )
        return {"execution_sequence": sequence}

    def generate_commands(state: SemanticSequencePlanningState) -> dict[str, Any]:
        target = state.get("asset_type") or "uav"
        commands = [
            command(
                "executeSubtask",
                target,
                {"subtask": item.get("task"), "order": index + 1},
            )
            for index, item in enumerate(state.get("execution_sequence", []))
        ]
        return {
            "commands": commands,
            "evaluation_metrics": {
                "Sub-task SR": "success rate of each ordered stage",
                "Executability": "physical-engine validity of generated action sequence",
                "Task Completion Time": "end-to-end duration for all subtasks",
            },
            "metadata": base_metadata(state, "semantic_sequence_planning"),
        }

    graph = state_graph(SemanticSequencePlanningState)
    graph.add_node("decompose_mission", decompose_mission)
    graph.add_node("enforce_order", enforce_order)
    graph.add_node("generate_commands", generate_commands)
    graph.add_edge(start, "decompose_mission")
    graph.add_edge("decompose_mission", "enforce_order")
    graph.add_edge("enforce_order", "generate_commands")
    graph.add_edge("generate_commands", end)
    return graph.compile()


AGENT_DEFINITION = AgentDefinition(
    name="semantic_sequence_planning",
    description="Decompose long-horizon missions into executable ordered subtasks.",
    builder=build_graph,
)
