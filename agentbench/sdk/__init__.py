"""Evaluation SDK contracts and lazy directory discovery/selection helpers."""

from .contracts import (
    EvaluationRunner, EvaluationSDKPlugin, SDK, SDKReport, SDKRun,
    SDKRunFactory, SDKRunnerContext, SDKTestInput, SDKReference,
    PreparedCase, PreparedCaseBatch, PreparationFailure, PartialCasePreparation,
    RunnerConcurrencyCapabilities, RunnerRecoveryCapabilities,
)

_PLUGIN_EXPORTS = {
    "EvaluationPlan", "SDKSelection", "evaluation_plan", "resolve_sdk",
}


def __getattr__(name):
    # Contracts work before the harness is imported, without SDK dependencies.
    if name == "discover_sdks":
        from .discovery import discover_sdks
        return discover_sdks
    if name in _PLUGIN_EXPORTS:
        from . import plugins
        return getattr(plugins, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "EvaluationRunner", "EvaluationSDKPlugin", "SDK", "SDKReport", "SDKRun",
    "SDKRunFactory", "SDKRunnerContext", "SDKTestInput", "SDKReference",
    "PreparedCase", "PreparedCaseBatch", "PreparationFailure", "PartialCasePreparation",
    "RunnerConcurrencyCapabilities", "RunnerRecoveryCapabilities",
    "discover_sdks", *sorted(_PLUGIN_EXPORTS),
]
