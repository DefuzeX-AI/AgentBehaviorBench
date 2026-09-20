"""Dispatch adapter-owned binding steps."""
from ..frameworks.registry import strategy

def steps(plan):
    return strategy(plan.get("framework", "langgraph")).binding_steps(plan)
