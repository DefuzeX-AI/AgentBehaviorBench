from typing import Dict, Any
from .state import AgentState


class BaseNode:
    def __call__(self, state: AgentState) -> Dict[str, Any]:
        raise NotImplementedError("Subclasses must implement __call__")