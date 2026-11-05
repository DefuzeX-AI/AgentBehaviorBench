"""Run-level model target provider contracts."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from importlib.metadata import entry_points
from functools import partial
from types import MappingProxyType
from typing import Mapping, Protocol, runtime_checkable
from urllib.parse import urlsplit

from .config import InterceptionConfigurationError
from .provider_catalog import load_provider_catalog


OPENROUTER_API_KEY_ENV = "OPENROUTER_API_KEY"
OPENROUTER_MODEL_ENV = "OPENROUTER_MODEL"
OPENROUTER_BASE_URL_ENV = "OPENROUTER_BASE_URL"
DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


@dataclass(frozen=True, slots=True)
class ModelTargetConfig:
    provider_id: str
    target_plugin: str
    base_url: str
    model: str
    credential_env: str
    headers: Mapping[str, str] = field(
        default_factory=lambda: MappingProxyType({})
    )

    endpoint_paths: Mapping[str, str] | None = None


@runtime_checkable
class ModelTargetProvider(Protocol):
    def resolve(self, environ: Mapping[str, str]) -> ModelTargetConfig:
        ...


@dataclass(frozen=True, slots=True)
class ConfiguredModelProvider:
    """Resolve a target using provider data, without provider-specific branches."""

    provider_id: str
    model: str | None = None

    def resolve(self, environ: Mapping[str, str]) -> ModelTargetConfig:
        definitions = load_provider_catalog(environ)["providers"]
        if self.provider_id not in definitions:
            raise InterceptionConfigurationError(f"Provider is not configured: {self.provider_id!r}")
        definition = definitions[self.provider_id]
        model_env = definition["model_env"]
        model = (self.model or environ.get("ABB_MODEL", "") or environ.get(model_env, "")).strip()
        if not model:
            raise InterceptionConfigurationError(
                f"{self.provider_id} model is required; pass --model or set {model_env}"
            )
        if any(character.isspace() for character in model):
            raise InterceptionConfigurationError("Model must not contain whitespace")
        base_env = definition["base_url_env"]
        base_url = environ.get(base_env, definition["base_url"]).strip()
        parsed = urlsplit(base_url)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment):
            raise InterceptionConfigurationError(
                f"{base_env} must be an absolute HTTPS URL without credentials, query or fragment"
            )
        headers = {header: environ[variable].strip()
                   for header, variable in definition.get("header_env", {}).items()
                   if environ.get(variable, "").strip()}
        endpoints = definition.get("endpoint_paths")
        return ModelTargetConfig(
            provider_id=self.provider_id,
            target_plugin=definition["target_plugin"],
            base_url=base_url.rstrip("/"),
            model=model,
            credential_env=definition["credential_env"],
            headers=MappingProxyType(headers),
            endpoint_paths=MappingProxyType(endpoints) if endpoints is not None else None,
        )


@dataclass(frozen=True, slots=True)
class OpenRouterProvider:
    """Compatibility entry point for callers explicitly requesting OpenRouter."""

    model: str | None = None

    def resolve(self, environ: Mapping[str, str]) -> ModelTargetConfig:
        return ConfiguredModelProvider("openrouter", self.model).resolve(environ)


MODEL_PROVIDER_ENTRY_POINT_GROUP = "defuzex_agentbench.model_providers"
MODEL_PROVIDER_ENV = "ABB_MODEL_PROVIDER"
DEFAULT_MODEL_PROVIDER = "openrouter"


def resolve_model_provider(
    name: str | None = None,
    *,
    model: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> ModelTargetProvider:
    """Construct the host model target provider selected by name.

    Explicit names win; otherwise inspect non-empty keys in catalog priority order.
    With no key, retain the first provider for the existing startup validation.
    Entry-point plugins remain available by explicit name; configured names win.
    """
    values = os.environ if environ is None else environ
    catalog = load_provider_catalog(values)
    definitions, priority = catalog["providers"], catalog["priority"]
    selected = (name or values.get(MODEL_PROVIDER_ENV, "")).strip().lower()
    if not selected:
        selected = next((key for key in priority
                         if values.get(definitions[key]["credential_env"], "").strip()), priority[0])
    factories: dict[str, object] = {
        key: partial(ConfiguredModelProvider, key) for key in definitions
    }
    # Preserve the public entry-point class for existing explicit OpenRouter callers.
    if DEFAULT_MODEL_PROVIDER in factories:
        factories[DEFAULT_MODEL_PROVIDER] = OpenRouterProvider
    registered = [entry for entry in entry_points(group=MODEL_PROVIDER_ENTRY_POINT_GROUP)
                  if entry.name.strip().lower() not in factories]
    if selected not in factories:
        entry = next((entry for entry in registered if entry.name.strip().lower() == selected), None)
        if entry is None:
            available = ", ".join(sorted({*factories, *(entry.name.strip().lower() for entry in registered)}))
            raise InterceptionConfigurationError(
                f"Unknown model target provider {selected!r}; available: {available}")
        factories[selected] = entry.load()
    provider = factories[selected](model=model)
    if not isinstance(provider, ModelTargetProvider):
        raise InterceptionConfigurationError(
            f"Model target provider {selected!r} does not implement resolve(environ)")
    return provider


@dataclass(frozen=True, slots=True)
class DeferredModelTargetProvider:
    """Resolve an optional replacement provider only when a runtime uses it."""

    model: str | None = None

    def resolve(self, environ: Mapping[str, str]) -> ModelTargetConfig:
        return resolve_model_provider(model=self.model, environ=environ).resolve(environ)


@dataclass(frozen=True, slots=True)
class StaticModelTargetProvider:
    """Supply an already validated target, primarily for deployments and tests."""

    target: ModelTargetConfig

    def resolve(self, environ: Mapping[str, str]) -> ModelTargetConfig:
        del environ
        return self.target
