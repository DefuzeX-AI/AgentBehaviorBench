"""Compatibility target name for existing OpenRouter deployments."""
from .compatible_json import CompatibleJSONTarget


class OpenRouterTarget(CompatibleJSONTarget):
    name = "openrouter"
