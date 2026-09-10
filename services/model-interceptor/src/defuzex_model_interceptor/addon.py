"""Proxy orchestration; per-call wire Strategies own protocol conversion."""
import time
import json
from urllib.parse import quote
from uuid import uuid4
from mitmproxy import http
from .auth import InterceptorAuthenticationError
from .events import emit, redact
from .registry import load_authentication, load_protocols, load_targets
from .targets import TargetRoutingError
from .capture import ResponseCapture
from .wire import json_bytes
from .policy import EgressPolicy


class ModelInterceptorAddon:
    def __init__(self, config):
        self.config = config
        self.protocols, self.authentication, self.targets = load_protocols(), load_authentication(), load_targets()
        self.policy = EgressPolicy(config)
        self.credentials = {c.credential_id: c for c in config.credentials}
        self.secrets = tuple(v for c in config.credentials for v in (c.token, c.secret))
        self._validate_plugins()

    def running(self):
        emit("interceptor_ready", agent_id=self.config.agent_id)

    def request(self, flow):
        route = self._route(flow)
        if route is None and self.policy.permits_tool(flow.request):
            # Bind tool egress to the approved Host, not a possibly different
            # transparent destination IP/SNI supplied by the caller.
            flow.request.host = flow.request.pretty_host.rstrip(".").lower()
            span = flow.request.headers.pop("x-abb-framework-span", None)
            tool = next(r for r in self.config.tool_routes if self.policy.matches(r, flow.request))
            flow.metadata.update(abb_tool=True, purpose=tool.purpose,
                defuzex_call_id=f"call_{uuid4().hex}", defuzex_started=time.monotonic(),
                framework_span_id=span if span and len(span) <= 64 else None,
                defuzex_source_host=flow.request.pretty_host,
                defuzex_source_path=flow.request.path.split('?', 1)[0])
            emit('tool_request', **self._tool_fields(flow), **self._body(flow.request))
            return
        span = flow.request.headers.pop("x-abb-framework-span", None)
        flow.metadata.update(defuzex_call_id=f"call_{uuid4().hex}", defuzex_started=time.monotonic(),
                             defuzex_source_host=flow.request.pretty_host,
                             defuzex_source_path=flow.request.path.split("?", 1)[0],
                             source_grpc=flow.request.headers.get("content-type", "").startswith("application/grpc"),
                             framework_span_id=span if span and len(span) <= 64 else None)
        if route is None:
            self._error(flow, "Undeclared network request blocked", 403)
            return
        flow.metadata["defuzex_route"] = route.route_id
        credential = self.credentials[route.credential_id]
        source_body = flow.request.content or b""
        try:
            # Stage authentication and routing on a copy. A plugin failure must
            # never send the real target credential to the original provider.
            outbound = flow.request.copy()
            authentication = self.authentication[credential.auth_plugin]
            if hasattr(authentication, "authorize_request"):
                authentication.authorize_request(outbound, temporary_token=credential.token, upstream_secret=credential.secret)
            else:
                authentication.authorize(outbound.headers, temporary_token=credential.token, upstream_secret=credential.secret)
            prepared = self.targets[self.config.target.target_plugin].prepare_request(
                outbound, route=route, target=self.config.target)
        except InterceptorAuthenticationError as exc:
            self._error(flow, str(exc), 401)
            return
        except Exception as exc:
            self._error(flow, str(exc), 422)
            return
        flow.request = outbound
        flow.metadata.update(wire=prepared.wire, defuzex_provider=prepared.provider_id,
                             defuzex_target_model=prepared.target_model, chunk_index=0)
        emit("llm_request", **self._fields(flow), source_model=prepared.source_model, model=prepared.target_model,
             source_payload=redact(prepared.source_payload, self.secrets), payload=redact(prepared.payload, self.secrets),
             source_raw_body=None if flow.metadata["source_grpc"] else redact(source_body.decode("utf-8", errors="replace"), self.secrets),
             source_transport="grpc" if flow.metadata["source_grpc"] else "http",
             raw_body=redact(flow.request.content.decode("utf-8"), self.secrets), truncated=False)

    def responseheaders(self, flow):
        wire = flow.metadata.get("wire")
        if wire is None or flow.response is None:
            return
        ct = flow.response.headers.get("content-type", "")
        flow.metadata.update(upstream_content_type=ct, upstream_status=flow.response.status_code)
        if "text/event-stream" not in ct.lower() or flow.response.status_code >= 400:
            return
        converter = wire.stream()
        capture = ResponseCapture(self.config.max_trace_bytes)
        flow.metadata["defuzex_capture"] = capture
        flow.response.headers.pop("content-length", None)
        flow.response.headers.pop("content-encoding", None)
        if getattr(wire, "grpc", False):
            flow.response.headers["content-type"] = "application/grpc"
            flow.response.trailers = http.Headers()
        elif not getattr(wire, "passthrough", False):
            flow.response.headers["content-type"] = wire.stream_type

        def stream(chunk):
            if flow.metadata.get("defuzex_stream_failed"):
                return [] if chunk else b""
            try:
                if chunk:
                    capture.write(chunk)
                forwarded = converter.feed(chunk)
                if forwarded:
                    flow.metadata["chunk_index"] += 1
                    emit("llm_chunk", agent_id=self.config.agent_id, call_id=flow.metadata["defuzex_call_id"],
                         sequence=flow.metadata["chunk_index"], upstream_bytes=len(chunk), client_bytes=len(forwarded),
                         elapsed_ms=round((time.monotonic()-flow.metadata["defuzex_started"])*1000, 3))
                if not chunk:
                    if getattr(wire, "grpc", False):
                        flow.response.trailers = http.Headers([(b"grpc-status", b"0")])
                    self._emit_response(flow, capture.finish(), streaming=True)
                    flow.metadata["defuzex_stream_emitted"] = True
                # mitmproxy 12 emits a terminating HTTP/1 chunk for ResponseData
                # b''. An empty iterable suppresses data while an SSE frame is
                # still incomplete; b'' is safe only at upstream EOF.
                return forwarded if forwarded or not chunk else []
            except Exception as exc:
                capture.close()
                flow.metadata["defuzex_stream_emitted"] = True
                flow.metadata["defuzex_stream_failed"] = True
                self._emit_error(flow, str(exc))
                if getattr(wire, "grpc", False):
                    flow.response.trailers = http.Headers([(b"grpc-status", b"13"), (b"grpc-message", quote(str(exc)).encode("ascii"))])
                    return [] if chunk else b""
                raise
        flow.response.stream = stream

    def response(self, flow):
        if flow.metadata.get('abb_tool') and flow.response is not None:
            emit('tool_response', **self._tool_fields(flow), status=flow.response.status_code,
                 latency_ms=round((time.monotonic()-flow.metadata['defuzex_started'])*1000, 3),
                 **self._body(flow.response))
            return
        wire = flow.metadata.get("wire")
        if wire is None or flow.response is None or flow.metadata.get("defuzex_stream_emitted"):
            return
        content = flow.response.content or b""
        status = flow.metadata.get("upstream_status", flow.response.status_code)
        flow.metadata["upstream_status"] = status
        try:
            payload = json.loads(content)
            if not isinstance(payload, dict):
                raise ValueError("Upstream response must be an object")
            translated = wire.response(payload, status)
            if status >= 400 or payload.get("error") or translated.get("error"):
                self._emit_response(flow, content, streaming=False)
                self._error(flow, str(translated.get("error", "Upstream error")), status if status >= 400 else 502)
                return
            if getattr(wire, "grpc", False):
                from .wire.grpc import pack_response
                flow.response.content = pack_response(translated)
                flow.response.headers["content-type"] = "application/grpc"
                flow.response.trailers = http.Headers([(b"grpc-status", b"0")])
                flow.response.headers.pop("content-length", None)
            elif not getattr(wire, "passthrough", False):
                flow.response.content = json_bytes(translated)
                flow.response.headers["content-type"] = "application/json"
            flow.metadata["client_payload"] = translated
            self._emit_response(flow, content, streaming=False)
        except Exception as exc:
            self._error(flow, "Response conversion failed: " + str(exc), 502)

    def _fields(self, flow):
        return dict(agent_id=self.config.agent_id, call_id=flow.metadata["defuzex_call_id"],
                    route_id=flow.metadata.get("defuzex_route"), method=flow.request.method,
                    source_host=flow.metadata.get("defuzex_source_host"),
                    source_path=flow.metadata.get("defuzex_source_path"), host=flow.request.pretty_host,
                    path=flow.request.path, provider=flow.metadata.get("defuzex_provider"),
                    framework_span_id=flow.metadata.get("framework_span_id"))

    def _tool_fields(self, flow):
        fields = self._fields(flow)
        # Query strings can carry credentials; retain the path and parsed body.
        fields['path'] = flow.request.path.split('?', 1)[0]
        fields['purpose'] = flow.metadata.get('purpose', 'tool')
        return fields

    def _body(self, message):
        content = message.content or b''
        content_type = message.headers.get('content-type', '')
        try:
            text = content.decode('utf-8')
        except UnicodeDecodeError:
            import base64
            return {'payload': {'encoding': 'base64', 'data': base64.b64encode(content).decode('ascii')},
                    'content_type': content_type, 'body_bytes': len(content), 'truncated': False}
        try:
            payload = redact(json.loads(text), self.secrets)
            raw = json.dumps(payload, ensure_ascii=False)
        except ValueError:
            if 'application/x-www-form-urlencoded' in content_type:
                from urllib.parse import parse_qs
                payload = redact(parse_qs(text, keep_blank_values=True), self.secrets)
                raw = json.dumps(payload, ensure_ascii=False)
            else:
                payload = raw = redact(text, self.secrets)
        return {'payload': payload, 'raw_body': raw, 'content_type': content_type,
                'body_bytes': len(content), 'truncated': False}

    def _emit_response(self, flow, content, *, streaming):
        route = next(r for r in self.config.routes if r.route_id == flow.metadata["defuzex_route"])
        payload = self.protocols[route.protocol_plugin].decode_response(
            content, flow.metadata.get("upstream_content_type", flow.response.headers.get("content-type", "")))
        emit("llm_response", **self._fields(flow),
             model=_model(payload) or flow.metadata.get("defuzex_target_model"),
             status=flow.metadata.get("upstream_status", flow.response.status_code),
             latency_ms=round((time.monotonic()-flow.metadata["defuzex_started"])*1000, 3),
             streaming=streaming, payload=redact(payload, self.secrets),
             client_payload=redact(flow.metadata.get("client_payload"), self.secrets),
             raw_body=redact(content.decode("utf-8", errors="replace"), self.secrets), truncated=False)

    def _emit_error(self, flow, message):
        emit("llm_error", agent_id=self.config.agent_id, call_id=flow.metadata["defuzex_call_id"],
             error=redact(message, self.secrets), framework_span_id=flow.metadata.get("framework_span_id"))

    def _error(self, flow, message, status):
        self._emit_error(flow, message)
        flow.metadata.pop("wire", None)
        if flow.metadata.get("source_grpc"):
            from .wire.grpc import status_code
            flow.response = http.Response.make(200, b"", {"content-type": "application/grpc",
                "grpc-status": str(status_code(status)), "grpc-message": quote(str(redact(message, self.secrets)))})
        else:
            flow.response = http.Response.make(status, json_bytes({"error": {"code": status, "message": redact(message, self.secrets)}}),
                                               {"content-type": "application/json"})

    def error(self, flow):
        capture = flow.metadata.pop("defuzex_capture", None)
        if capture:
            capture.close()
        if flow.metadata.get('abb_tool'):
            emit('tool_error', **self._tool_fields(flow), error=redact(str(flow.error), self.secrets))
        elif "defuzex_call_id" in flow.metadata:
            self._emit_error(flow, str(flow.error))

    def _route(self, flow):
        return next((r for r in self.config.routes if self.policy.matches(r, flow.request)), None)

    def _validate_plugins(self):
        missing = ({r.protocol_plugin for r in self.config.routes} - self.protocols.keys()
                   | {c.auth_plugin for c in self.config.credentials} - self.authentication.keys()
                   | {self.config.target.target_plugin} - self.targets.keys())
        if missing:
            raise RuntimeError("Unknown model interceptor plugins: " + ", ".join(sorted(missing)))


def _model(payload):
    return payload.get("model") if isinstance(payload, dict) else None
