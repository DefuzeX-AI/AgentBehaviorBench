"""Host-side plugin contracts for Agent trust bootstrapping."""

from __future__ import annotations

from importlib.metadata import entry_points
from typing import Mapping, Protocol, runtime_checkable

from .config import InterceptionConfigurationError


TRUST_ENTRY_POINT_GROUP = "defuzex.model_interceptor.trust"


@runtime_checkable
class TrustPlugin(Protocol):
    name: str

    def agent_environment(self, certificate_path: str) -> Mapping[str, str]:
        ...


class PemEnvironmentTrust:
    name = "pem-env"

    def agent_environment(self, certificate_path: str) -> Mapping[str, str]:
        return {
            "SSL_CERT_FILE": certificate_path,
            "REQUESTS_CA_BUNDLE": certificate_path,
            "NODE_EXTRA_CA_CERTS": certificate_path,
            "GRPC_DEFAULT_SSL_ROOTS_FILE_PATH": certificate_path,
        }


def get_trust_plugin(name: str) -> TrustPlugin:
    normalized = name.strip().lower()
    plugins: dict[str, TrustPlugin] = {"pem-env": PemEnvironmentTrust()}
    for entry_point in entry_points(group=TRUST_ENTRY_POINT_GROUP):
        loaded = entry_point.load()
        plugin = loaded() if isinstance(loaded, type) else loaded
        plugin_name = getattr(plugin, "name", "").strip().lower()
        if plugin_name:
            plugins[plugin_name] = plugin
    try:
        return plugins[normalized]
    except KeyError as exc:
        raise InterceptionConfigurationError(
            f"Unknown model interceptor trust plugin: {name!r}"
        ) from exc
