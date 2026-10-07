"""Open-vocabulary target navigation task.

Goal: given a natural-language target description, generate an exploration and
navigation plan for a single embodied asset such as UAV, UGV, or robot dog.
"""

from typing import Any, TypedDict

from app.modules.agents.definition import AgentDefinition
from app.modules.agents.graphs import import_langgraph
from app.modules.agents.tasks.common import base_metadata, command


class OpenVocabNavigationState(TypedDict, total=False):
    """State for instruction-driven target search and navigation."""

    instruction: str
    asset_type: str
    search_regions: list[str]
    exploration_plan: list[dict[str, Any]]
    commands: list[dict[str, Any]]
    evaluation_metrics: dict[str, str]
    metadata: dict[str, Any]


def build_graph():
    """Build the open-vocabulary navigation graph."""

    start, end, state_graph = import_langgraph()

    def parse_instruction(state: OpenVocabNavigationState) -> dict[str, Any]:
        instruction = state.get("instruction", "")
        regions = state.get("search_regions") or ["unknown_region"]
        asset_type = state.get("asset_type") or "uav"
        return {
            "asset_type": asset_type,
            "exploration_plan": [
                {
                    "step": "semantic_scan",
                    "asset": asset_type,
                    "region": region,
                    "objective": instruction,
                }
                for region in regions
            ],
        }

    def generate_commands(state: OpenVocabNavigationState) -> dict[str, Any]:
        commands = [
            command(
                "semanticNavigate",
                state.get("asset_type", "uav"),
                {
                    "objective": step["objective"],
                    "region": step["region"],
                    "mode": "explore_then_approach",
                },
            )
            for step in state.get("exploration_plan", [])
        ]
        return {"commands": commands}

    def attach_metrics(state: OpenVocabNavigationState) -> dict[str, Any]:
        return {
            "evaluation_metrics": {
                "SR": "success rate of reaching the described target",
                "SPL": "path efficiency compared with shortest feasible path",
                "Semantic Gaps": "missed key-region ratio during exploration",
            },
            "metadata": base_metadata(state, "open_vocab_navigation"),
        }

    graph = state_graph(OpenVocabNavigationState)
    graph.add_node("parse_instruction", parse_instruction)
    graph.add_node("generate_commands", generate_commands)
    graph.add_node("attach_metrics", attach_metrics)
    graph.add_edge(start, "parse_instruction")
    graph.add_edge("parse_instruction", "generate_commands")
    graph.add_edge("generate_commands", "attach_metrics")
    graph.add_edge("attach_metrics", end)
    return graph.compile()


AGENT_DEFINITION = AgentDefinition(
    name="open_vocab_navigation",
    description="Instruction-driven exploration and navigation to an open-vocabulary target.",
    builder=build_graph,
)
