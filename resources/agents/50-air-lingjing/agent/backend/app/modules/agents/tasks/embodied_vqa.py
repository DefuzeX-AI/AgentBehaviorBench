"""Embodied visual question answering task.

Goal: plan active sensing actions for a single embodied asset, gather visual
evidence, and return an answer plan for scene-level questions.
"""

from typing import Any, TypedDict

from app.modules.agents.definition import AgentDefinition
from app.modules.agents.graphs import import_langgraph
from app.modules.agents.tasks.common import base_metadata, command


class EmbodiedVqaState(TypedDict, total=False):
    """State for active perception and question answering."""

    question: str
    asset_type: str
    candidate_viewpoints: list[dict[str, Any]]
    sensing_plan: list[dict[str, Any]]
    commands: list[dict[str, Any]]
    answer: str
    evaluation_metrics: dict[str, str]
    metadata: dict[str, Any]


def build_graph():
    """Build the embodied VQA graph."""

    start, end, state_graph = import_langgraph()

    def plan_viewpoints(state: EmbodiedVqaState) -> dict[str, Any]:
        viewpoints = state.get("candidate_viewpoints") or [
            {"name": "overview", "priority": 1},
            {"name": "close_inspection", "priority": 2},
        ]
        return {
            "sensing_plan": [
                {
                    "step": index + 1,
                    "viewpoint": viewpoint,
                    "purpose": f"collect evidence for: {state.get('question', '')}",
                }
                for index, viewpoint in enumerate(viewpoints)
            ]
        }

    def generate_commands(state: EmbodiedVqaState) -> dict[str, Any]:
        target = state.get("asset_type") or "uav"
        return {
            "commands": [
                command(
                    "activePerception",
                    target,
                    {"viewpoint": step["viewpoint"], "purpose": step["purpose"]},
                )
                for step in state.get("sensing_plan", [])
            ]
        }

    def draft_answer(state: EmbodiedVqaState) -> dict[str, Any]:
        return {
            "answer": "pending_visual_evidence",
            "evaluation_metrics": {
                "Answer Accuracy": "correctness after evidence collection",
                "Navigation Steps": "number of movement steps before answering",
                "Viewpoint Quality": "clarity and usefulness of final viewpoint",
            },
            "metadata": base_metadata(state, "embodied_vqa"),
        }

    graph = state_graph(EmbodiedVqaState)
    graph.add_node("plan_viewpoints", plan_viewpoints)
    graph.add_node("generate_commands", generate_commands)
    graph.add_node("draft_answer", draft_answer)
    graph.add_edge(start, "plan_viewpoints")
    graph.add_edge("plan_viewpoints", "generate_commands")
    graph.add_edge("generate_commands", "draft_answer")
    graph.add_edge("draft_answer", end)
    return graph.compile()


AGENT_DEFINITION = AgentDefinition(
    name="embodied_vqa",
    description="Plan active sensing actions and answer scene-level visual questions.",
    builder=build_graph,
)
