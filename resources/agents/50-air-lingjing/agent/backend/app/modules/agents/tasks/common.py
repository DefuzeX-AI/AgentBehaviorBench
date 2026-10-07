"""Shared helpers for task-design LangGraph workflows."""

from typing import Any


def as_list(value: Any) -> list[Any]:
    """Normalize optional scalar/list inputs into a list."""

    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def base_metadata(state: dict[str, Any], graph_name: str) -> dict[str, Any]:
    """Attach common LangGraph metadata to a task output."""

    return {
        **state.get("metadata", {}),
        "graph": graph_name,
        "framework": "langgraph",
    }


def command(command_type: str, target: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Build a UE/ENGINE friendly command envelope."""

    return {
        "commandType": command_type,
        "target": target,
        "payload": payload,
    }
