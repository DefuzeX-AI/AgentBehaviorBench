"""Compatibility alias for sdk.common.case_identity."""
import sys
from agentbench.sdk.common import case_identity as _implementation
sys.modules[__name__] = _implementation
