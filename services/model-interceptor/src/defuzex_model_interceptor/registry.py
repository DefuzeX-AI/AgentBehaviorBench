"""Plugin discovery for service-side protocol and authentication behavior."""

from __future__ import annotations

from importlib.metadata import entry_points
from typing import Protocol, runtime_checkable


PROTOCOL_GROUP = "defuzex.model_interceptor.protocols"
AUTH_GROUP = "defuzex.model_interceptor.auth"
TARGET_GROUP = "defuzex.model_interceptor.targets"


@runtime_checkable
class ProtocolPlugin(Protocol):
    name: str

    def decode_request(self, content: bytes, content_type: str) -> object:
        ...

    def decode_response(self, content: bytes, content_type: str) -> object:
        ...


@runtime_checkable
class AuthenticationPlugin(Protocol):
    name: str

    def authorize(self, headers: object, *, temporary_token: str, upstream_secret: str) -> None:
        ...


@runtime_checkable
class TargetProviderPlugin(Protocol):
    name: str

    def prepare_request(self, request: object, *, route: object, target: object) -> object:
        ...


def load_protocols() -> dict[str, ProtocolPlugin]:
    from .protocols import (
        ANTHROPIC_MESSAGES_PROTOCOL,
        JSON_HTTP_PROTOCOL,
        OPENAI_CHAT_PROTOCOL,
        OPENAI_RESPONSES_PROTOCOL,
        GEMINI_CONTENT_PROTOCOL,
    )

    plugins: dict[str, ProtocolPlugin] = {
        JSON_HTTP_PROTOCOL.name: JSON_HTTP_PROTOCOL,
        OPENAI_CHAT_PROTOCOL.name: OPENAI_CHAT_PROTOCOL,
        OPENAI_RESPONSES_PROTOCOL.name: OPENAI_RESPONSES_PROTOCOL,
        ANTHROPIC_MESSAGES_PROTOCOL.name: ANTHROPIC_MESSAGES_PROTOCOL,
        GEMINI_CONTENT_PROTOCOL.name: GEMINI_CONTENT_PROTOCOL,
    }
    return _load(PROTOCOL_GROUP, plugins)


def load_authentication() -> dict[str, AuthenticationPlugin]:
    from .auth import ANTHROPIC_API_KEY_AUTH, BEARER_TOKEN_AUTH, GOOGLE_API_KEY_AUTH

    plugins: dict[str, AuthenticationPlugin] = {
        BEARER_TOKEN_AUTH.name: BEARER_TOKEN_AUTH,
        ANTHROPIC_API_KEY_AUTH.name: ANTHROPIC_API_KEY_AUTH,
        GOOGLE_API_KEY_AUTH.name: GOOGLE_API_KEY_AUTH,
    }
    return _load(AUTH_GROUP, plugins)


def load_targets() -> dict[str, TargetProviderPlugin]:
    from .targets import OPENROUTER_TARGET

    plugins: dict[str, TargetProviderPlugin] = {
        OPENROUTER_TARGET.name: OPENROUTER_TARGET,
    }
    return _load(TARGET_GROUP, plugins)


def _load(group: str, plugins: dict[str, object]) -> dict:  # type: ignore[type-arg]
    for entry_point in entry_points(group=group):
        loaded = entry_point.load()
        plugin = loaded() if isinstance(loaded, type) else loaded
        name = getattr(plugin, "name", "").strip().lower()
        if name:
            plugins[name] = plugin
    return plugins
