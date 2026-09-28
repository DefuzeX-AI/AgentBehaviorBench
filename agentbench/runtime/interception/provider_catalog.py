"""Validated, deployment-overridable model provider declarations."""
from pathlib import Path
from collections.abc import Mapping

from .config import InterceptionConfigurationError, tomllib

PROVIDER_CATALOG_ENV = "ABB_MODEL_PROVIDERS_CONFIG"
DEFAULT_PROVIDER_CATALOG = Path(__file__).with_name("model-providers.toml")


def load_provider_catalog(environ: Mapping[str, str]) -> dict:
    path = Path(environ.get(PROVIDER_CATALOG_ENV, "").strip() or DEFAULT_PROVIDER_CATALOG)
    try:
        with path.open("rb") as stream:
            catalog = tomllib.load(stream)
    except (OSError, ValueError) as exc:
        raise InterceptionConfigurationError("Cannot read model provider configuration") from exc
    definitions, priority = catalog.get("providers"), catalog.get("priority")
    if not isinstance(definitions, dict) or not definitions:
        raise InterceptionConfigurationError("Model providers must be a non-empty table")
    if (not isinstance(priority, list) or not priority
            or any(not isinstance(name, str) or name not in definitions for name in priority)
            or len(set(priority)) != len(priority)):
        raise InterceptionConfigurationError("Provider priority must name distinct configured providers")
    required = {"credential_env", "model_env", "base_url_env", "base_url", "target_plugin"}
    for name, definition in definitions.items():
        if (not name or name != name.strip().lower() or not isinstance(definition, dict)
                or set(definition) - required - {"header_env", "endpoint_paths"}
                or any(not isinstance(definition.get(key), str) or not definition[key].strip()
                       for key in required)):
            raise InterceptionConfigurationError(f"Invalid model provider definition: {name!r}")
        for field in ("header_env", "endpoint_paths"):
            mapping = definition.get(field, {})
            if not isinstance(mapping, dict) or any(
                not isinstance(k, str) or not k.strip() or not isinstance(v, str) or not v.strip()
                for k, v in mapping.items()
            ):
                raise InterceptionConfigurationError(f"Invalid {field} for provider {name!r}")
        if "endpoint_paths" in definition and (not definition["endpoint_paths"] or any(
            not key.startswith("/") or not value.startswith("/") or value.startswith("//")
            or "?" in value or "#" in value or ".." in value.split("/")
            for key, value in definition["endpoint_paths"].items()
        )):
            raise InterceptionConfigurationError(f"Invalid endpoint paths for provider {name!r}")
    return catalog
