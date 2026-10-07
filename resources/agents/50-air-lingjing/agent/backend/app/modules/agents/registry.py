"""Registry for available LangGraph agent workflows."""

from importlib import import_module
from pkgutil import iter_modules
from typing import Any

from app.core.responses import AppError
from app.modules.agents.definition import AgentDefinition
from app.modules.agents import tasks


def _discover_agents() -> dict[str, AgentDefinition]:
    """Import every task file and collect its `AGENT_DEFINITION`."""

    registry: dict[str, AgentDefinition] = {}
    for module_info in iter_modules(tasks.__path__):
        if module_info.ispkg:
            continue
        module = import_module(f"{tasks.__name__}.{module_info.name}")
        definition = getattr(module, "AGENT_DEFINITION", None)
        if definition is None:
            continue
        registry[definition.name] = definition
    return registry


AGENT_REGISTRY: dict[str, AgentDefinition] = _discover_agents()


def list_agents() -> list[dict[str, str]]:
    """Return graph metadata without importing LangGraph itself."""

    return [
        {"name": definition.name, "description": definition.description}
        for definition in AGENT_REGISTRY.values()
    ]


def get_agent(name: str) -> AgentDefinition:
    """Fetch a registered agent definition or raise a Java-style API error."""

    try:
        return AGENT_REGISTRY[name]
    except KeyError as exc:
        raise AppError(f"\u667a\u80fd\u4f53\u4e0d\u5b58\u5728: {name}") from exc


async def invoke_agent(name: str, state: dict[str, Any]) -> dict[str, Any]:
    """Compile and execute a registered LangGraph workflow."""

    definition = get_agent(name)
    graph = definition.builder()
    result = await graph.ainvoke(state)
    return dict(result)
