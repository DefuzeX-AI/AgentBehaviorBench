"""Evaluation SDK contracts and lazy plugin selection helpers."""

from .contracts import (
    EvaluationRunner, EvaluationSDKPlugin, SDK, SDKReport, SDKRun,
    SDKRunFactory, SDKRunnerContext, SDKTestInput,
)

_PLUGIN_EXPORTS = {
    "SDK_ENTRY_POINT_GROUP", "SDK_PLUGIN_API_VERSION", "EvaluationPlan",
    "SDKReference", "SDKSelection", "evaluation_plan", "installed_sdk_references",
    "resolve_sdk",
}


def __getattr__(name):
    # Contracts work before the harness is imported, without SDK dependencies.
    if name in _PLUGIN_EXPORTS:
        from . import plugins
        return getattr(plugins, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "EvaluationRunner", "EvaluationSDKPlugin", "SDK", "SDKReport", "SDKRun",
    "SDKRunFactory", "SDKRunnerContext", "SDKTestInput", *sorted(_PLUGIN_EXPORTS),
]
