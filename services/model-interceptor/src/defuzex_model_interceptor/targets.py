"""Built-in upstream target provider adapters."""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urlsplit

from .config import Route, Target


class TargetRoutingError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PreparedTargetRequest:
    provider_id: str
    source_model: object
    target_model: str
    host: str
    path: str
    payload: object


class OpenRouterTarget:
    name = "openrouter"

    _ENDPOINTS = {
        "openai-chat": "/chat/completions",
        "openai-responses": "/responses",
        "anthropic-messages": "/messages",
        "gemini-content": "/chat/completions",
    }

    def prepare_request(
        self,
        request: object,
        *,
        route: Route,
        target: Target,
    ) -> PreparedTargetRequest:
        try:
            endpoint = self._ENDPOINTS[route.protocol_plugin]
        except KeyError as exc:
            raise TargetRoutingError(
                f"OpenRouter does not support source protocol {route.protocol_plugin!r}"
            ) from exc

        content = getattr(request, "content", b"") or b""
        try:
            payload = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TargetRoutingError("Model request body must be valid UTF-8 JSON") from exc
        if not isinstance(payload, dict):
            raise TargetRoutingError("Model request body must be a JSON object")

        source_model = payload.get("model")
        if route.protocol_plugin == "gemini-content":
            from .gemini import request_to_chat
            source_path = getattr(request, "path")
            source_model = source_path.split("/models/", 1)[-1].split(":", 1)[0]
            try:
                payload = request_to_chat(payload, streaming=":streamGenerateContent" in source_path)
            except (ValueError, KeyError, TypeError) as exc:
                raise TargetRoutingError(str(exc)) from exc
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
        )


OPENROUTER_TARGET = OpenRouterTarget()
