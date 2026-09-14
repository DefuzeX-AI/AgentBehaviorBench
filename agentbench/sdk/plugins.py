"""Select directory-discovered SDK adapters and normalize execution plans."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from agentbench.harness.errors import ProviderSelectionError

from .contracts import (
    EvaluationSDKPlugin,
    SDK_PLUGIN_API_VERSION,
    SDKReference,
)
from .contracts import SDKRunnerContext as SDKRunnerContext
from .discovery import discover_sdks, load_sdk


@dataclass(frozen=True, slots=True)
class SDKSelection:
    """A resolved SDK value plus its identity for diagnostics."""

    reference: SDKReference
    value: object


@dataclass(frozen=True, slots=True)
class EvaluationPlan:
    """One SDK selection and a defensive, read-only copy of its options."""

    selection: SDKSelection
    options: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "options", MappingProxyType(dict(self.options)))


def resolve_sdk(spec: str | None = None) -> SDKSelection:
    """Select and load one adapter from the SDK directory.

    Args:
        spec: Directory name, matched case-insensitively after trimming
            whitespace. If omitted, exactly one adapter must be discovered.
            Import strings and installed package entry points are not accepted.

    Returns:
        The selected plugin instance and its directory-derived identity.

    Raises:
        ProviderSelectionError: If the selection is empty, unknown, ambiguous,
            or the selected adapter cannot be loaded or violates the interface.
    """
    requested = None if spec is None else spec.strip()
    if requested == "":
        raise ProviderSelectionError("SDK selection cannot be empty")
    references = discover_sdks()
    if not references:
        raise ProviderSelectionError(
            "No SDK adapters found. Add an adapter package with __init__.py "
            "and plugin.py under agentbench/sdk/."
        )
    choices = ", ".join(reference.name for reference in references)
    if requested is None:
        if len(references) != 1:
            raise ProviderSelectionError(
                f"Multiple SDK adapters found: {choices}. Select one with --sdk NAME "
                "or resolve_sdk(NAME) in Python."
            )
        reference = references[0]
    else:
        reference = next(
            (
                item
                for item in references
                if item.name.casefold() == requested.casefold()
            ),
            None,
        )
        if reference is None:
            raise ProviderSelectionError(
                f"Unknown SDK {requested!r}. Available adapters: {choices}. "
                "SDK names must match a directory under agentbench/sdk/."
            )
    value = load_sdk(reference)
    if isinstance(value, type) or not isinstance(value, EvaluationSDKPlugin):
        raise ProviderSelectionError(
            f"SDK {reference.name!r} must export a plugin instance implementing "
            "api_version, execution, and create_benchmark_runner()."
        )
    plugin_execution(value)
    return SDKSelection(reference=reference, value=value)


def python_sdk_selection(sdk: object) -> SDKSelection:
    """Validate an SDK object explicitly supplied by a Python caller.

    This override does not register an adapter or change directory discovery.
    Raw SDK objects must expose create_run(); adapter instances implement
    EvaluationSDKPlugin. Neither is imported automatically from a string.
    """
    plugin_execution(sdk)
    module = getattr(sdk, "__module__", None)
    name = getattr(sdk, "__qualname__", None) or getattr(sdk, "__name__", None)
    reference = (
        f"{module}:{name}"
        if module and name
        else str(
            getattr(sdk, "__name__", None)
            or f"{type(sdk).__module__}:{type(sdk).__qualname__}"
        )
    )
    return SDKSelection(
        reference=SDKReference(name=reference, source="python", object_ref=reference),
        value=sdk,
    )


def evaluation_plan(
    *,
    sdk: object | None = None,
    selection: SDKSelection | None = None,
    options: Mapping[str, object] | None = None,
) -> EvaluationPlan:
    """Build a normalized evaluation plan for CLI and Python callers.

    At most one SDK source may be supplied. Without an explicit source, the
    sole directory-discovered adapter is selected; there is no named default.
    All parameters are keyword-only.

    Args:
        sdk: An already imported Python SDK object exposing create_run(), or
            an EvaluationSDKPlugin instance. Must not be supplied together
            with selection. Objects are validated, not implicitly constructed.
        selection: A previously resolved SDKSelection, normally produced by
            resolve_sdk(name). Must not be supplied together with sdk.
        options: SDK-specific configuration forwarded to its runner factory.
            A defensive shallow copy is stored as a read-only mapping; None
            means no options. The adapter owns defaults and option validation.

    Returns:
        An EvaluationPlan containing the SDK selection and read-only options.

    Raises:
        ValueError: If sdk and selection are both supplied.
        ProviderSelectionError: If automatic selection is missing or ambiguous,
            loading fails, or a supplied SDK violates the supported interface.
    """
    if sdk is not None and selection is not None:
        raise ValueError("Pass sdk or selection, not both")
    resolved = selection
    if resolved is None:
        resolved = resolve_sdk() if sdk is None else python_sdk_selection(sdk)
    else:
        plugin_execution(resolved.value)
    return EvaluationPlan(
        selection=resolved, options={} if options is None else options
    )


def plugin_execution(value: object) -> Literal["container", "local"]:
    """Validate an SDK's interface and return its execution location.

    Adapter-shaped objects are checked strictly: an invalid adapter must not
    silently fall back to the plain create_run() interface.
    """
    if isinstance(value, type):
        raise ProviderSelectionError("Pass an SDK instance, not a class")
    if any(
        hasattr(value, field)
        for field in (
            "create_benchmark_runner",
            "api_version",
            "execution",
        )
    ):
        if not callable(getattr(value, "create_benchmark_runner", None)):
            raise ProviderSelectionError(
                "SDK plugin must expose create_benchmark_runner()"
            )
        if getattr(value, "api_version", None) != SDK_PLUGIN_API_VERSION:
            raise ProviderSelectionError(
                f"Unsupported SDK plugin API version: {getattr(value, 'api_version', None)!r}"
            )
        execution = getattr(value, "execution", None)
        if execution not in ("container", "local"):
            raise ProviderSelectionError(
                f"Unsupported SDK plugin execution mode: {execution!r}"
            )
        return execution
    if not callable(getattr(value, "create_run", None)):
        raise ProviderSelectionError(
            "SDK must expose create_run(), or implement EvaluationSDKPlugin"
        )
    return "local"
