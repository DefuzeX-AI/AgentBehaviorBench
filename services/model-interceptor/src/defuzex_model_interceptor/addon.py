"""mitmproxy addon for matched model authentication and semantic tracing."""

from __future__ import annotations

import fnmatch
import time
import json
from uuid import uuid4

from mitmproxy import http

from .auth import InterceptorAuthenticationError
from .config import Route, ServiceConfig
from .events import emit, redact
from .registry import load_authentication, load_protocols, load_targets
from .targets import TargetRoutingError
from .capture import ResponseCapture


class ModelInterceptorAddon:
    def __init__(self, config: ServiceConfig) -> None:
        self.config = config
        self.protocols = load_protocols()
        self.authentication = load_authentication()
        self.targets = load_targets()
        self.credentials = {item.credential_id: item for item in config.credentials}
        self.secrets = tuple(
            value for item in config.credentials for value in (item.token, item.secret)
        )
        self._validate_plugins()

    def running(self) -> None:
        emit("interceptor_ready", agent_id=self.config.agent_id)

    def request(self, flow: http.HTTPFlow) -> None:
        route = self._route(flow)
        if route is None:
            return
        call_id = f"call_{uuid4().hex}"
        flow.metadata["defuzex_route"] = route.route_id
        flow.metadata["defuzex_call_id"] = call_id
        flow.metadata["defuzex_started"] = time.monotonic()
        span_id = flow.request.headers.pop("x-abb-framework-span", None)
        # IDs are correlation hints, never authentication or proof of trace coverage.
        flow.metadata["framework_span_id"] = span_id if span_id and len(span_id) <= 64 else None
        flow.metadata["defuzex_source_host"] = flow.request.pretty_host
        flow.metadata["defuzex_source_path"] = flow.request.path.split("?", 1)[0]
        source_body = flow.request.content or b""
        if route.protocol_plugin == "gemini-content":
            flow.metadata["gemini"] = True
            flow.metadata["gemini_sse"] = "alt=sse" in flow.request.path
        credential = self.credentials[route.credential_id]
        try:
            self.authentication[credential.auth_plugin].authorize(
                flow.request.headers,
                temporary_token=credential.token,
                upstream_secret=credential.secret,
            )
        except InterceptorAuthenticationError as exc:
            flow.response = http.Response.make(
                401,
                str(exc).encode("utf-8"),
                {"Content-Type": "text/plain; charset=utf-8"},
            )
            return
        try:
            prepared = self.targets[self.config.target.target_plugin].prepare_request(
                flow.request,
                route=route,
                target=self.config.target,
            )
        except TargetRoutingError as exc:
            content = flow.request.content or b""
            payload = self.protocols[route.protocol_plugin].decode_request(
                content, flow.request.headers.get("content-type", "")
            )
            emit(
                "llm_request",
                agent_id=self.config.agent_id,
                call_id=call_id,
                route_id=route.route_id,
                method=flow.request.method,
                host=flow.metadata["defuzex_source_host"],
                path=flow.metadata["defuzex_source_path"],
                provider=self.config.target.provider_id,
                model=_model(payload),
                payload=redact(payload, self.secrets),
                source_raw_body=redact(source_body.decode("utf-8", errors="replace"), self.secrets),
                raw_body=redact(content.decode("utf-8", errors="replace"), self.secrets),
                routing_error=str(exc),
                truncated=False,
            )
            flow.response = http.Response.make(
                422,
                str(exc).encode("utf-8"),
                {"Content-Type": "text/plain; charset=utf-8"},
            )
            return
        flow.metadata["defuzex_provider"] = prepared.provider_id
        flow.metadata["defuzex_target_model"] = prepared.target_model
        content = flow.request.content or b""
        payload = self.protocols[route.protocol_plugin].decode_request(
            content, flow.request.headers.get("content-type", "")
        )
        emit(
            "llm_request",
            agent_id=self.config.agent_id,
            call_id=call_id,
            route_id=route.route_id,
            method=flow.request.method,
            source_host=flow.metadata["defuzex_source_host"],
            source_path=flow.metadata["defuzex_source_path"],
            host=prepared.host,
            path=prepared.path,
            provider=prepared.provider_id,
            source_model=prepared.source_model,
            model=prepared.target_model,
            payload=redact(payload, self.secrets),
            source_raw_body=redact(source_body.decode("utf-8", errors="replace"), self.secrets),
            raw_body=redact(content.decode("utf-8", errors="replace"), self.secrets),
            truncated=False,
            framework_span_id=flow.metadata.get("framework_span_id"),
        )

    def responseheaders(self, flow: http.HTTPFlow) -> None:
        if "defuzex_route" not in flow.metadata or flow.response is None:
            return
        content_type = flow.response.headers.get("content-type", "")
        flow.metadata["upstream_content_type"] = content_type
        if "text/event-stream" not in content_type.lower():
            return
        captured = ResponseCapture(self.config.max_trace_bytes)
        flow.metadata["defuzex_capture"] = captured
        converter = None
        if flow.metadata.get("gemini") and flow.response.status_code < 400:
            from .gemini import GeminiStream
            converter = GeminiStream(sse=flow.metadata["gemini_sse"])
            flow.response.headers["content-type"] = (
                "text/event-stream; charset=utf-8" if flow.metadata["gemini_sse"] else "application/json; charset=utf-8")
            flow.response.headers.pop("content-length", None)

        def stream(chunk: bytes) -> bytes:
            try:
                if chunk:
                    captured.write(chunk)
                forwarded = converter.feed(chunk) if converter is not None else chunk
            except (ValueError, OSError) as exc:
                captured.close()
                flow.metadata["defuzex_stream_emitted"] = True
                emit("llm_error", agent_id=self.config.agent_id,
                     call_id=flow.metadata["defuzex_call_id"], error=redact(str(exc), self.secrets),
                     framework_span_id=flow.metadata.get("framework_span_id"))
                raise
            if not chunk:
                self._emit_response(flow, captured.finish(), False, streaming=True)
                flow.metadata["defuzex_stream_emitted"] = True
            return forwarded

        flow.response.stream = stream

    def response(self, flow: http.HTTPFlow) -> None:
        if "defuzex_route" not in flow.metadata or flow.response is None:
            return
        if flow.metadata.get("defuzex_stream_emitted"):
            return
        content = flow.response.content or b""
        self._emit_response(flow, content, False, streaming=False)
        if flow.metadata.get("gemini"):
            from .gemini import response_from_chat
            try:
                payload = response_from_chat(json.loads(flow.response.content or b"{}"), status=flow.response.status_code)
            except (ValueError, TypeError, KeyError) as exc:
                flow.response.status_code = 502
                payload = {"error": {"code": 502, "message": str(exc), "status": "INTERNAL"}}
            flow.response.content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            flow.response.headers["content-type"] = "application/json; charset=utf-8"

    def _emit_response(
        self, flow: http.HTTPFlow, content: bytes, truncated: bool, *, streaming: bool
    ) -> None:
        route = next(
            item for item in self.config.routes if item.route_id == flow.metadata["defuzex_route"]
        )
        payload = self.protocols[route.protocol_plugin].decode_response(
            content,
            flow.metadata.get("upstream_content_type", "" if flow.response is None else flow.response.headers.get("content-type", "")),
        )

        started = float(flow.metadata.get("defuzex_started", time.monotonic()))
        emit(
            "llm_response",
            agent_id=self.config.agent_id,
            call_id=flow.metadata["defuzex_call_id"],
            route_id=route.route_id,
            method=flow.request.method,
            source_host=flow.metadata.get("defuzex_source_host"),
            source_path=flow.metadata.get("defuzex_source_path"),
            host=flow.request.pretty_host,
            path=flow.request.path,
            provider=flow.metadata.get(
                "defuzex_provider", self.config.target.provider_id
            ),
            model=_model(payload) or flow.metadata.get("defuzex_target_model"),
            status=None if flow.response is None else flow.response.status_code,
            latency_ms=round((time.monotonic() - started) * 1000, 3),
            streaming=streaming,
            payload=redact(payload, self.secrets),
            raw_body=redact(content.decode("utf-8", errors="replace"), self.secrets),
            truncated=truncated,
            framework_span_id=flow.metadata.get("framework_span_id"),
        )

    def error(self, flow: http.HTTPFlow) -> None:
        capture = flow.metadata.pop("defuzex_capture", None)
        if capture is not None:
            capture.close()
        if "defuzex_call_id" in flow.metadata:
            emit("llm_error", agent_id=self.config.agent_id,
                 call_id=flow.metadata["defuzex_call_id"],
                 error=redact(str(flow.error), self.secrets),
                 framework_span_id=flow.metadata.get("framework_span_id"))

    def _route(self, flow: http.HTTPFlow) -> Route | None:
        host = flow.request.pretty_host.rstrip(".").lower()
        method = flow.request.method.upper()
        for route in self.config.routes:
            if (
                flow.request.port in route.ports
                and method in route.methods
                and any(fnmatch.fnmatchcase(host, pattern) for pattern in route.host_patterns)
                and any(fnmatch.fnmatchcase(flow.request.path, pattern) for pattern in route.path_patterns)
            ):
                return route
        return None

    def _validate_plugins(self) -> None:
        missing_protocols = {
            route.protocol_plugin for route in self.config.routes if route.protocol_plugin not in self.protocols
        }
        missing_auth = {
            credential.auth_plugin
            for credential in self.config.credentials
            if credential.auth_plugin not in self.authentication
        }
        missing_targets = (
            {self.config.target.target_plugin}
            if self.config.target.target_plugin not in self.targets
            else set()
        )
        if missing_protocols or missing_auth or missing_targets:
            missing = sorted(missing_protocols | missing_auth | missing_targets)
            raise RuntimeError(f"Unknown model interceptor plugins: {', '.join(missing)}")


def _model(payload: object) -> object:
    return payload.get("model") if isinstance(payload, dict) else None
