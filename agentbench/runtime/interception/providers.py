"""Run-level model target provider contracts."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from importlib.metadata import entry_points
from types import MappingProxyType
from typing import Mapping, Protocol, runtime_checkable
from urllib.parse import urlsplit

from .config import InterceptionConfigurationError


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


@runtime_checkable
class ModelTargetProvider(Protocol):
    def resolve(self, environ: Mapping[str, str]) -> ModelTargetConfig:
        ...


@dataclass(frozen=True, slots=True)
class OpenRouterProvider:
    """Resolve one model-controlled OpenRouter target for a benchmark run."""

    model: str | None = None

    def resolve(self, environ: Mapping[str, str]) -> ModelTargetConfig:
        model = (self.model or environ.get(OPENROUTER_MODEL_ENV, "")).strip()
        if not model:
            raise InterceptionConfigurationError(
                "OpenRouter model is required; pass --model or set OPENROUTER_MODEL"
            )
        if any(character.isspace() for character in model):
            raise InterceptionConfigurationError(
                f"OpenRouter model must not contain whitespace: {model!r}"
            )

        base_url = environ.get(
            OPENROUTER_BASE_URL_ENV, DEFAULT_OPENROUTER_BASE_URL
        ).strip()
        parsed = urlsplit(base_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise InterceptionConfigurationError(
                "OPENROUTER_BASE_URL must be an absolute HTTPS URL"
            )

        headers: dict[str, str] = {}
        referer = environ.get("OPENROUTER_HTTP_REFERER", "").strip()
        title = environ.get("OPENROUTER_APP_TITLE", "").strip()
        if referer:
            headers["HTTP-Referer"] = referer
        if title:
            headers["X-OpenRouter-Title"] = title

        return ModelTargetConfig(
            provider_id="openrouter",
            target_plugin="openrouter",
            base_url=base_url.rstrip("/"),
            model=model,
            credential_env=OPENROUTER_API_KEY_ENV,
            headers=MappingProxyType(headers),
        )


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

    The name comes from ``name``, else ``ABB_MODEL_PROVIDER``, else ``openrouter``.
    Providers other than the built-in one register a factory accepting ``model=``
    under the ``defuzex_agentbench.model_providers`` entry-point group, like the
    interceptor's other plugin layers; a plugin cannot replace a built-in name.
    """
    values = os.environ if environ is None else environ
    selected = (name or values.get(MODEL_PROVIDER_ENV, "") or DEFAULT_MODEL_PROVIDER).strip().lower()
    factories: dict[str, object] = {DEFAULT_MODEL_PROVIDER: OpenRouterProvider}
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
class StaticModelTargetProvider:
    """Supply an already validated target, primarily for deployments and tests."""

    target: ModelTargetConfig

    def resolve(self, environ: Mapping[str, str]) -> ModelTargetConfig:
        del environ
        return self.target
