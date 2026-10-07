"""HTTP API for LangGraph agent discovery and execution."""

from typing import Any

from fastapi import APIRouter

from app.core.responses import json_success
from app.modules.agents.registry import invoke_agent, list_agents

router = APIRouter(prefix="/api/agents")


@router.get("")
def get_agents():
    """List registered LangGraph workflows available in this service."""

    return json_success(list_agents())


@router.post("/{agent_name}/invoke")
async def invoke(agent_name: str, payload: dict[str, Any]):
    """Invoke one registered LangGraph workflow with caller-provided state."""

    return json_success(await invoke_agent(agent_name, payload))
