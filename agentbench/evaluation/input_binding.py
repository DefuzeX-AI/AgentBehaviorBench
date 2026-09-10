"""Compatibility alias for sdk.common.input_binding."""
import sys
from agentbench.sdk.common import input_binding as _implementation
sys.modules[__name__] = _implementation
