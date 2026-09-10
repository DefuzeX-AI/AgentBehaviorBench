"""Compatibility alias for sdk.common.conversation."""
import sys
from agentbench.sdk.common import conversation as _implementation
sys.modules[__name__] = _implementation
