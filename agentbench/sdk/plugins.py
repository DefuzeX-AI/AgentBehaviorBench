"""Discover evaluation SDK plugins and build immutable execution plans."""

from __future__ import annotations

import importlib
import importlib.metadata
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from agentbench.harness.errors import ProviderSelectionError
from .contracts import EvaluationSDKPlugin, SDKRunnerContext


SDK_ENTRY_POINT_GROUP = "defuzex_agentbench.evaluation_sdks"
SDK_PLUGIN_API_VERSION = "agentbench.evaluation_sdk.v1"


@dataclass(frozen=True, slots=True)
class SDKReference:
    """Stable provenance for one SDK selection."""

    name: str
    source: Literal["builtin", "entry-point", "python"]
    object_ref: str
    distribution: str | None = None
    version: str | None = None

    @property
    def qualified_name(self) -> str:
        if self.distribution is None:
            return self.name
        return f"{self.distribution}::{self.name}"


@dataclass(frozen=True, slots=True)
class SDKSelection:
    """A resolved SDK value plus the provenance needed for diagnostics."""

    reference: SDKReference
    value: object


@dataclass(frozen=True, slots=True)
class EvaluationPlan:
    """One composition-root decision consumed by the execution builder."""

    selection: SDKSelection
    options: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "options", MappingProxyType(dict(self.options)))


def builtin_sdk_selection(name="kuma") -> SDKSelection:
    """Return the official KUMA adapter without importing KUMA itself."""

    if name == "panda":
        from .panda import plugin
    else:
        from .kuma import plugin

    return SDKSelection(
        reference=SDKReference(
            name=plugin.name,
            source="builtin",
            object_ref=f"agentbench.sdk.{name}:plugin",
            distribution="defuzex-agentbench",
            version=_distribution_version("defuzex-agentbench"),
        ),
        value=plugin,
    )


def python_sdk_selection(
    sdk: object, *, object_ref: str | None = None
) -> SDKSelection:
    """Adapt an SDK object already present in the calling interpreter."""

    plugin_execution(sdk)
    reference = object_ref or _python_object_ref(sdk)
    return SDKSelection(
        reference=SDKReference(
            name=reference,
            source="python",
            object_ref=reference,
        ),
        value=sdk,
    )


def evaluation_plan(
    *,
    sdk: object | None = None,
    selection: SDKSelection | None = None,
    options: Mapping[str, object] | None = None,
) -> EvaluationPlan:
    """Normalize Python and CLI composition roots to one execution plan."""

    if sdk is not None and selection is not None:
        raise ValueError("Pass sdk or selection, not both")
    resolved = selection
    if resolved is None:
        resolved = (
            builtin_sdk_selection() if sdk is None else python_sdk_selection(sdk)
        )
    return EvaluationPlan(selection=resolved, options=options or {})


def installed_sdk_references(
    *, entry_points_provider: Callable[[], object] | None = None
) -> tuple[SDKReference, ...]:
    """Read installed plugin metadata without importing third-party code."""

    points = _sdk_entry_points(entry_points_provider)
    references = [_reference_for_entry_point(point) for point in points]
    references.append(builtin_sdk_selection().reference)
    references.append(builtin_sdk_selection("panda").reference)
    unique = {
        (
            reference.source,
            reference.distribution,
            reference.name,
            reference.object_ref,
        ): reference
        for reference in references
    }
    return tuple(
        sorted(
            unique.values(),
            key=lambda item: (
                item.name.casefold(),
                item.distribution or "",
                item.object_ref,
            ),
        )
    )


def resolve_sdk(
    spec: str,
    *,
    entry_points_provider: Callable[[], object] | None = None,
) -> SDKSelection:
    """Resolve a built-in, installed entry point, or explicit Python import."""

    requested = spec.strip()
    if not requested:
        raise ProviderSelectionError("SDK selection cannot be empty")
    if requested.casefold() in {"kuma", "panda"}:
        return builtin_sdk_selection(requested.casefold())
    if requested.startswith("python:"):
        return _load_python_sdk(requested.removeprefix("python:"), explicit=True)

    distribution, separator, name = requested.partition("::")
    if separator:
        if not distribution or not name or "::" in name:
            raise ProviderSelectionError(
                "Qualified SDK names must use DISTRIBUTION::NAME"
            )
        matches = [
            point
            for point in _sdk_entry_points(entry_points_provider)
            if point.name == name
            and _normalized_distribution(_entry_point_distribution(point))
            == _normalized_distribution(distribution)
        ]
        return _load_entry_point(requested, matches)

    matches = [
        point
        for point in _sdk_entry_points(entry_points_provider)
        if point.name == requested
    ]
    if matches:
        return _load_entry_point(requested, matches)

    # Compatibility for the original --sdk MODULE[:OBJECT] interface. New CLI
    # usage should spell this as python:MODULE[:OBJECT] so locality is explicit.
    return _load_python_sdk(requested, explicit=False)


def plugin_execution(value: object) -> Literal["container", "local"]:
    """Return the execution locality exposed by a selected SDK value."""

    if isinstance(value, EvaluationSDKPlugin):
        if value.api_version != SDK_PLUGIN_API_VERSION:
            raise ProviderSelectionError(
                f"Unsupported SDK plugin API version: {value.api_version!r}"
            )
        if value.execution not in {"container", "local"}:
            raise ProviderSelectionError(
                f"Unsupported SDK plugin execution mode: {value.execution!r}"
            )
        return value.execution
    _validate_loaded_sdk(value)
    return "local"


def _load_entry_point(requested: str, matches: list[object]) -> SDKSelection:
    if not matches:
        raise ProviderSelectionError(
            f"No installed evaluation SDK matches {requested!r}"
        )
    if len(matches) > 1:
        choices = ", ".join(
            sorted(
                f"{_entry_point_distribution(point)}::{point.name}"
                for point in matches
            )
        )
        raise ProviderSelectionError(
            f"Evaluation SDK {requested!r} is ambiguous; choose one of: {choices}"
        )
    point = matches[0]
    try:
        loaded = point.load()
        value = loaded() if isinstance(loaded, type) else loaded
        plugin_execution(value)
    except ProviderSelectionError:
        raise
    except Exception as exc:
        raise ProviderSelectionError(
            f"Could not load evaluation SDK {requested!r}"
        ) from exc
    return SDKSelection(reference=_reference_for_entry_point(point), value=value)


def _load_python_sdk(spec: str, *, explicit: bool) -> SDKSelection:
    module_name, separator, attribute = spec.partition(":")
    if not module_name or (separator and not attribute):
        prefix = "python:" if explicit else ""
        raise ProviderSelectionError(
            f"SDK import must use {prefix}MODULE or {prefix}MODULE:OBJECT"
        )
    try:
        value = importlib.import_module(module_name)
        if separator:
            value = getattr(value, attribute)
    except (ImportError, AttributeError) as exc:
        hint = (
            " Install a plugin or use python:MODULE[:OBJECT]."
            if not explicit
            else ""
        )
        raise ProviderSelectionError(
            f"Could not import evaluation SDK {spec!r}.{hint}"
        ) from exc
    plugin_execution(value)
    object_ref = f"{module_name}:{attribute}" if separator else module_name
    selection = python_sdk_selection(value, object_ref=object_ref)
    if explicit:
        return selection
    return SDKSelection(
        reference=SDKReference(
            name=selection.reference.name,
            source="python",
            object_ref=selection.reference.object_ref,
        ),
        value=selection.value,
    )


def _validate_loaded_sdk(value: object) -> None:
    if isinstance(value, type) or not callable(getattr(value, "create_run", None)):
        raise ProviderSelectionError(
            "SDK must expose create_run(), or implement EvaluationSDKPlugin"
        )


def _sdk_entry_points(
    provider: Callable[[], object] | None,
) -> tuple[object, ...]:
    result = (provider or importlib.metadata.entry_points)()
    if hasattr(result, "select"):
        return tuple(result.select(group=SDK_ENTRY_POINT_GROUP))
    if isinstance(result, Mapping):
        return tuple(result.get(SDK_ENTRY_POINT_GROUP, ()))
    return tuple(
        point
        for point in result  # type: ignore[union-attr]
        if getattr(point, "group", None) == SDK_ENTRY_POINT_GROUP
    )


def _reference_for_entry_point(point: object) -> SDKReference:
    distribution = _entry_point_distribution(point)
    dist = getattr(point, "dist", None)
    return SDKReference(
        name=str(point.name),
        source="entry-point",
        object_ref=str(point.value),
        distribution=distribution,
        version=getattr(dist, "version", None),
    )


def _entry_point_distribution(point: object) -> str:
    dist = getattr(point, "dist", None)
    metadata = getattr(dist, "metadata", None)
    if metadata is not None:
        name = metadata.get("Name")
        if name:
            return str(name)
    name = getattr(dist, "name", None)
    return str(name or "unknown-distribution")


def _distribution_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _normalized_distribution(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).casefold()


def _python_object_ref(value: object) -> str:
    module = getattr(value, "__module__", None)
    name = getattr(value, "__qualname__", None) or getattr(value, "__name__", None)
    if module and name:
        return f"{module}:{name}"
    module_name = getattr(value, "__name__", None)
    return str(module_name or type(value).__name__)
