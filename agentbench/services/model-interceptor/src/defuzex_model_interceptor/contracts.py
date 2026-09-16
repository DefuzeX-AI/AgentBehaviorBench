"""Contracts shared by proxy orchestration and concrete adapters."""
from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class SourceSignature:
    """Adapter-owned request recognition, independent of Agent route declarations.

    Matching identifies a protocol, not authorization: the proxy must still
    validate the request against a configured per-run credential before sending
    anything to its configured model target. Paths exclude query parameters.
    """

    paths: tuple[str, ...]
    auth_plugin: str
    content_type: str = "application/json"
    method: str = "POST"

    def matches(self, request) -> bool:
        media = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        return (request.method.upper() == self.method
                and (media == self.content_type or media.startswith(self.content_type + "+"))
                and any(fnmatchcase(request.path.split("?", 1)[0], path) for path in self.paths))

    def specificity(self, request) -> int:
        """Prefer longer literal paths when protocol suffix patterns overlap."""
        path = request.path.split("?", 1)[0]
        return max((len(pattern.replace("*", "")) for pattern in self.paths
                    if fnmatchcase(path, pattern)), default=0)


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


class ResponseStream(Protocol):
    """A per-call stream decoder; an empty chunk signals upstream EOF."""

    def feed(self, chunk: bytes) -> bytes:
        ...


class WireStrategy(Protocol):
    """Model conversion independent of the proxy's HTTP flow objects.

    decode initializes per-call state, including source_model. Strategies may
    advertise passthrough or grpc for transport handling; converted HTTP
    streams also expose stream_type.
    """

    endpoint: str
    response_type: str
    source_model: object

    def decode(self, request: object) -> tuple[dict, dict]:
        ...

    def response(self, payload: dict, status: int) -> dict:
        ...

    def stream(self) -> ResponseStream:
        ...


class GrpcWireStrategy(WireStrategy, Protocol):
    """A strategy that also encodes a unary protobuf response envelope."""

    grpc: bool

    def encode_response(self, payload: dict) -> bytes:
        ...


@dataclass(frozen=True, slots=True)
class PreparedTargetRequest:
    provider_id: str
    source_model: object
    target_model: str
    host: str
    path: str
    payload: object
    source_payload: object = None
    wire: WireStrategy | None = None
