"""Shared state schemas for LangGraph agent workflows."""

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    """Minimal state passed between graph nodes.

    Future agents can extend this state with domain-specific keys such as
    `task_id`, `scene_id`, `tool_results`, or long-running execution metadata.
    """

    input: str
    output: str
    metadata: dict[str, Any]


class UavReconState(TypedDict, total=False):
    """State for the UAV fire reconnaissance task."""

    image_base64: str
    ai_response: str
    parsed_response: dict[str, Any]
    result: bool
    metadata: dict[str, Any]


class UavRoutePlanState(TypedDict, total=False):
    """State for the UAV route planning task."""

    image_base64: str
    map_base64: str
    messages: list[dict[str, Any]]
    ai_response: str
    route_plan: dict[str, Any]
    dispatched_command: dict[str, Any]
    metadata: dict[str, Any]
