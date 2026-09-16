"""Transparent model interception configuration and lifecycle contracts."""

from .config import (
    CredentialConfig,
    InterceptionConfig,
    InterceptionConfigurationError,
    RouteConfig,
)
from .image import InterceptorImageProvider, StaticInterceptorImageProvider
from .plugins import TrustPlugin, get_trust_plugin
from .providers import (
    DEFAULT_OPENROUTER_BASE_URL,
    MODEL_PROVIDER_ENTRY_POINT_GROUP,
    MODEL_PROVIDER_ENV,
    OPENROUTER_API_KEY_ENV,
    OPENROUTER_BASE_URL_ENV,
    OPENROUTER_MODEL_ENV,
    ModelTargetConfig,
    ModelTargetProvider,
    OpenRouterProvider,
    StaticModelTargetProvider,
    resolve_model_provider,
)
from .session import RunningModelInterceptor
from .trace import (
    DEFAULT_TRACE_MAX_BYTES,
    InterceptionTraceState,
    NullTraceSink,
    TraceEvent,
    TraceSink,
)

__all__ = [
    "CredentialConfig",
    "DEFAULT_TRACE_MAX_BYTES",
    "InterceptionConfig",
    "InterceptionConfigurationError",
    "InterceptionTraceState",
    "InterceptorImageProvider",
    "ModelTargetConfig",
    "ModelTargetProvider",
    "NullTraceSink",
    "OpenRouterProvider",
    "OPENROUTER_API_KEY_ENV",
    "OPENROUTER_BASE_URL_ENV",
    "OPENROUTER_MODEL_ENV",
    "DEFAULT_OPENROUTER_BASE_URL",
    "RouteConfig",
    "RunningModelInterceptor",
    "StaticInterceptorImageProvider",
    "StaticModelTargetProvider",
    "TraceEvent",
    "TraceSink",
    "TrustPlugin",
    "get_trust_plugin",
    "MODEL_PROVIDER_ENTRY_POINT_GROUP",
    "MODEL_PROVIDER_ENV",
    "resolve_model_provider",
]
