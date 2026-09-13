"""Prepare model requests for the configured OpenRouter endpoint."""
from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from urllib.parse import urlsplit
from ..config import Route, Target
from ..contracts import PreparedTargetRequest, WireStrategy
from ..error import TargetRoutingError


class OpenRouterTarget:
    name = "openrouter"

    def __init__(self, wires: Mapping[str, Callable[[], WireStrategy]]):
        self.wires = wires

    def prepare_request(
        self,
        request: object,
        *,
        route: Route,
        target: Target,
    ) -> PreparedTargetRequest:
        try:
            wire = self.wires[route.protocol_plugin]()
            endpoint = wire.endpoint
        except KeyError as exc:
            raise TargetRoutingError(
                f"OpenRouter does not support source protocol {route.protocol_plugin!r}"
            ) from exc

        try:
            source, payload = wire.decode(request)
        except (ValueError, KeyError, TypeError) as exc:
            raise TargetRoutingError(str(exc)) from exc
        source_model = wire.source_model
        payload["model"] = target.model
        parsed = urlsplit(target.base_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise TargetRoutingError("OpenRouter target base URL must use HTTPS")
        base_path = parsed.path.rstrip("/")
        target_path = f"{base_path}{endpoint}"

        setattr(request, "scheme", "https")
        setattr(request, "host", parsed.hostname)
        setattr(request, "port", parsed.port or 443)
        setattr(request, "path", target_path)
        setattr(
            request,
            "content",
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            ),
        )
        headers = getattr(request, "headers")
        headers["content-type"] = "application/json"
        headers["accept-encoding"] = "identity"
        for key in list(headers):
            if key.lower().startswith("grpc-") or key.lower() in {"te", "x-goog-request-params", "content-encoding"}:
                headers.pop(key, None)
        headers["host"] = parsed.netloc
        for key, value in target.headers.items():
            headers[key] = value

        return PreparedTargetRequest(
            provider_id=target.provider_id,
            source_model=source_model,
            target_model=target.model,
            host=parsed.hostname,
            path=target_path,
            payload=payload,
            source_payload=source,
            wire=wire,
        )
