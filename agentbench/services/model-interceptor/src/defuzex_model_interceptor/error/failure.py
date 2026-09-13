"""Serializable interceptor failures, independent of mitmproxy and the host runtime."""

from dataclasses import asdict, dataclass
from enum import Enum



class ErrorCode(str, Enum):
    EGRESS_DENIED = "egress_denied"
    AUTHENTICATION_FAILED = "authentication_failed"
    REQUEST_PREPARATION_FAILED = "request_preparation_failed"
    UPSTREAM_ERROR = "upstream_error"
    RESPONSE_CONVERSION_FAILED = "response_conversion_failed"
    STREAM_PROCESSING_FAILED = "stream_processing_failed"
    TRANSPORT_ERROR = "transport_error"

    @property
    def stage(self) -> str:
        return {
            self.EGRESS_DENIED: "policy",
            self.AUTHENTICATION_FAILED: "authentication",
            self.REQUEST_PREPARATION_FAILED: "request_preparation",
            self.UPSTREAM_ERROR: "upstream",
            self.RESPONSE_CONVERSION_FAILED: "response_conversion",
            self.STREAM_PROCESSING_FAILED: "stream_processing",
            self.TRANSPORT_ERROR: "transport",
        }[self]


class RequestKind(str, Enum):
    MODEL = "model"
    TOOL = "tool"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class InterceptionFailure:
    """Failure evidence carried over the existing trace event protocol.

    local_status is the HTTP-equivalent status chosen by the interceptor;
    gRPC can transport it with HTTP 200. upstream_status is only populated
    when an upstream HTTP response was actually received.
    """

    code: ErrorCode
    message: str
    call_id: str
    request_kind: RequestKind = RequestKind.UNKNOWN
    source_host: str | None = None
    source_port: int | None = None
    source_path: str | None = None
    method: str | None = None
    route_id: str | None = None
    provider: str | None = None
    target_host: str | None = None
    target_port: int | None = None
    target_path: str | None = None
    local_status: int | None = None
    upstream_status: int | None = None

    def to_event_fields(self) -> dict[str, object]:
        """Return JSON-safe fields; the observation layer redacts before output."""
        fields = asdict(self)
        fields.pop("code")
        fields.pop("message")
        fields.update(error_code=self.code.value, error_stage=self.code.stage,
                      error=self.message, request_kind=self.request_kind.value)
        for key in ("source_path", "target_path"):
            if fields[key] is not None:
                fields[key] = fields[key].split("?", 1)[0].split("#", 1)[0]
        return fields


class InterceptorAuthenticationError(PermissionError):
    """The presented per-run credential was rejected."""


class TargetRoutingError(ValueError):
    """The selected target cannot prepare this request."""
