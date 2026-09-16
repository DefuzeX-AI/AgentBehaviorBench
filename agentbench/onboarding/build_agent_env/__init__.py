"""Generate reviewable Agent integration files without executing Agent source."""

from .service import BuildResult, build_agent_environment

__all__ = ["BuildResult", "build_agent_environment"]
