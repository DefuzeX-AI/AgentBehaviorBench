from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command


@dataclass(frozen=True)
class WorkflowRuntimeConfig:
    """
    Shared runtime config helper for LangGraph.
    `thread_id` is the durable key for checkpointed execution.
    """

    thread_id: str

    def to_langgraph_config(self) -> dict[str, Any]:
        return {"configurable": {"thread_id": self.thread_id}}


class CheckpointManager:
    """
    Centralized checkpoint and workflow invocation helpers.
    - Provides MemorySaver for graph compilation.
    - Standardizes invoke/resume/cancel command patterns.
    """

    def __init__(self) -> None:
        self._checkpointer = MemorySaver()

    @property
    def checkpointer(self) -> MemorySaver:
        return self._checkpointer

    def invoke(
        self,
        *,
        graph: Any,
        state: dict[str, Any],
        thread_id: str,
    ) -> dict[str, Any]:
        return graph.invoke(state, config=WorkflowRuntimeConfig(thread_id=thread_id).to_langgraph_config())

    def resume(
        self,
        *,
        graph: Any,
        resume_payload: dict[str, Any],
        thread_id: str,
    ) -> dict[str, Any]:
        return graph.invoke(
            Command(resume=resume_payload),
            config=WorkflowRuntimeConfig(thread_id=thread_id).to_langgraph_config(),
        )

    def cancel(
        self,
        *,
        graph: Any,
        thread_id: str,
    ) -> dict[str, Any]:
        """
        Cooperative cancel command:
        workflow routes should check `status == cancelled` and stop scheduling new nodes.
        """
        return graph.invoke(
            {"status": "cancelled"},
            config=WorkflowRuntimeConfig(thread_id=thread_id).to_langgraph_config(),
        )
