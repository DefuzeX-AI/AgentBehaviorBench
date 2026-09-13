"""Contracts shared by proxy orchestration and concrete adapters."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


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
