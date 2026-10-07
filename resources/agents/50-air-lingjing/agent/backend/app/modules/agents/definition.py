"""Shared metadata type for LangGraph task registration."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AgentDefinition:
    """Metadata and factory for one registered LangGraph workflow."""

    name: str
    description: str
    builder: Callable[[], Any]
