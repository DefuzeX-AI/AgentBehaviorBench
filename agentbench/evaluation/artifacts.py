"""Compatibility alias for sdk.common.artifacts."""
import sys
from agentbench.sdk.common import artifacts as _implementation
sys.modules[__name__] = _implementation
