"""Composition root for built-in adapters and installed plugins.

Plugins may export an instance, a class, or a zero-argument factory.
Wire plugins remain per-call factories, so stream state is never shared.
"""
from importlib.metadata import entry_points
from .contracts import AuthenticationPlugin, ProtocolPlugin, TargetProviderPlugin

PROTOCOL_GROUP = "defuzex.model_interceptor.protocols"
AUTH_GROUP = "defuzex.model_interceptor.auth"
TARGET_GROUP = "defuzex.model_interceptor.targets"


def create_openrouter_target():
    from .targets.openrouter import OpenRouterTarget
    return OpenRouterTarget(load_wires())


def load_protocols() -> dict[str, ProtocolPlugin]:
    from .observation.decoders import (
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
    for name in ("gemini-grpc", "ollama-chat", "ollama-generate", "openai-completions", "openai-embeddings"):
        plugins[name] = JSON_HTTP_PROTOCOL
    return _load(PROTOCOL_GROUP, plugins)


def load_authentication() -> dict[str, AuthenticationPlugin]:
    from .security.auth import BEARER_TOKEN_AUTH, NetworkIsolatedAuthentication
    from model.anthropic.auth import ANTHROPIC_API_KEY_AUTH
    from model.google.auth import GOOGLE_API_KEY_AUTH

    plugins: dict[str, AuthenticationPlugin] = {
        BEARER_TOKEN_AUTH.name: BEARER_TOKEN_AUTH,
        ANTHROPIC_API_KEY_AUTH.name: ANTHROPIC_API_KEY_AUTH,
        GOOGLE_API_KEY_AUTH.name: GOOGLE_API_KEY_AUTH,
        "network-isolated": NetworkIsolatedAuthentication(),
    }
    return _load(AUTH_GROUP, plugins)


def load_targets() -> dict[str, TargetProviderPlugin]:
    target = create_openrouter_target()

    plugins: dict[str, TargetProviderPlugin] = {
        target.name: target,
    }
    return _load(TARGET_GROUP, plugins)


def _load(group: str, plugins: dict[str, object]) -> dict:  # type: ignore[type-arg]
    for entry_point in entry_points(group=group):
        loaded = entry_point.load()
        is_factory = isinstance(loaded, type) or (
            callable(loaded) and not getattr(loaded, "name", None)
        )
        plugin = loaded() if is_factory else loaded
        name = getattr(plugin, "name", "").strip().lower()
        if name:
            plugins[name] = plugin
    return plugins


def load_wires():
    from model.ollama import OllamaWire
    from model.google.gemini import GeminiWire
    from model.native import NativeJsonWire
    registry = {
        "openai-chat": lambda: NativeJsonWire("/chat/completions"),
        "openai-responses": lambda: NativeJsonWire("/responses", "response.completed"),
        "anthropic-messages": lambda: NativeJsonWire("/messages", "message_stop"),
        "openai-completions": lambda: NativeJsonWire("/completions"),
        "openai-embeddings": lambda: NativeJsonWire("/embeddings"),
        "gemini-content": GeminiWire,
        "gemini-grpc": lambda: GeminiWire(grpc=True),
        "ollama-chat": OllamaWire,
        "ollama-generate": lambda: OllamaWire(generate=True),
    }
    for entry in entry_points(group="defuzex.model_interceptor.wires"):
        if entry.name in registry:
            raise ValueError("Duplicate wire strategy: " + entry.name)
        registry[entry.name] = entry.load()
    return registry
