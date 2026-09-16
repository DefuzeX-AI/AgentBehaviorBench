"""Registered command features exposed by the AgentBench CLI."""

from .base import CommandFeature
from .agent import FEATURE as AGENT_FEATURE
from .certify import FEATURE as CERTIFY_FEATURE
from .run import FEATURE as RUN_FEATURE
from .view import FEATURE as VIEW_FEATURE
from .observe import FEATURE as OBSERVE_FEATURE
from .evaluate import FEATURE as EVALUATE_FEATURE
from .clean import FEATURE as CLEAN_FEATURE
from .sdk import FEATURE as SDK_FEATURE
from .resume import FEATURE as RESUME_FEATURE, RETRY_FEATURE
from .reuse import FEATURE as REUSE_FEATURE

FEATURES: tuple[CommandFeature, ...] = (
    RUN_FEATURE,
    AGENT_FEATURE,
    VIEW_FEATURE,
    CERTIFY_FEATURE,
    OBSERVE_FEATURE,
    EVALUATE_FEATURE,
    CLEAN_FEATURE,
    SDK_FEATURE,
    RESUME_FEATURE,
    RETRY_FEATURE,
    REUSE_FEATURE,
)

__all__ = ["FEATURES", "CommandFeature"]
