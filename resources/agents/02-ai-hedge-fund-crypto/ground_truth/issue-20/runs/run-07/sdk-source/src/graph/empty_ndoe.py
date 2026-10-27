"""
Merged data node.
"""
from typing import Dict, Any
from .base_node import BaseNode, AgentState


class EmptyNode(BaseNode):
    def __call__(self, state: AgentState) -> Dict[str, Any]:
        """
        EmptyNode
        """
        return state
