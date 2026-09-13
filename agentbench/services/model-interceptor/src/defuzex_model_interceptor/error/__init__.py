"""Public error contracts."""
from .failure import (
    ErrorCode, InterceptionFailure, InterceptorAuthenticationError,
    RequestKind, TargetRoutingError,
)

__all__ = ["ErrorCode", "InterceptionFailure", "InterceptorAuthenticationError",
           "RequestKind", "TargetRoutingError"]
