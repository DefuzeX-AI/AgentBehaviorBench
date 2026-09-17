"""Proxy orchestration; per-call wire Strategies own protocol conversion."""
import time
import json
from urllib.parse import quote
from uuid import uuid4
from mitmproxy import http
from ..observation.events import emit, failure_fields
from ..security.redaction import redact
from ..error import ErrorCode, InterceptionFailure, InterceptorAuthenticationError, RequestKind, TargetRoutingError
from ..registry import load_authentication, load_protocols, load_targets, load_wires
from ..observation.capture import ResponseCapture
from ..transport.json import json_bytes
from ..routing.policy import EgressPolicy
from ..routing.automatic import AutomaticModelRouter


class ModelInterceptorAddon:
    def __init__(self, config):
        self.config = config
        self.protocols, self.authentication, self.targets = load_protocols(), load_authentication(), load_targets()
        self.policy = EgressPolicy(config)
        self.credentials = {c.credential_id: c for c in config.credentials}
        self.secrets = tuple(v for c in config.credentials for v in (c.token, c.secret))
        self._validate_plugins()
        self.automatic = AutomaticModelRouter(load_wires(), config.credentials, self.authentication)

    def running(self):
        emit("interceptor_ready", agent_id=self.config.agent_id)

    def request(self, flow):
        span = flow.request.headers.pop("x-abb-framework-span", None)
        flow.metadata.update(defuzex_call_id=f"call_{uuid4().hex}", defuzex_started=time.monotonic(),
                             defuzex_source_host=flow.request.pretty_host,
                             defuzex_source_port=flow.request.port,
                             defuzex_source_path=flow.request.path.split("?", 1)[0],
                             source_grpc=flow.request.headers.get("content-type", "").startswith("application/grpc"),
                             framework_span_id=span if span and len(span) <= 64 else None)
        try:
            route = self._route(flow)
        except InterceptorAuthenticationError as exc:
            self._error(flow, str(exc), 401, code=ErrorCode.AUTHENTICATION_FAILED)
            return
        except TargetRoutingError as exc:
            self._error(flow, str(exc), 422, code=ErrorCode.REQUEST_PREPARATION_FAILED)
            return
        if route is None and self.policy.permits_tool(flow.request):
            # Bind tool egress to the approved Host, not a possibly different
            # transparent destination IP/SNI supplied by the caller.
            flow.request.host = flow.request.pretty_host.rstrip(".").lower()
            tool = next(r for r in self.config.tool_routes if self.policy.matches(r, flow.request))
            flow.metadata.update(abb_tool=True, purpose=tool.purpose)
            emit('tool_request', **self._tool_fields(flow), **self._body(flow.request))
            return
        if route is None:
            self._error(flow, "Undeclared network request blocked", 403, code=ErrorCode.EGRESS_DENIED)
            return
        flow.metadata["defuzex_route"] = route.route_id
        flow.metadata["defuzex_resolved_route"] = route
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
            self._error(flow, str(exc), 401, code=ErrorCode.AUTHENTICATION_FAILED)
            return
        except Exception as exc:
            self._error(flow, str(exc), 422, code=ErrorCode.REQUEST_PREPARATION_FAILED)
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
                self._emit_error(flow, str(exc), code=ErrorCode.STREAM_PROCESSING_FAILED)
                if getattr(wire, "grpc", False):
                    flow.response.trailers = http.Headers([(b"grpc-status", b"13"), (b"grpc-message", quote(str(redact(str(exc), self.secrets))).encode("ascii"))])
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
                self._error(flow, str(translated.get("error", "Upstream error")), status if status >= 400 else 502,
                            code=ErrorCode.UPSTREAM_ERROR)
                return
            if getattr(wire, "grpc", False):
                flow.response.content = wire.encode_response(translated)
                flow.response.headers["content-type"] = "application/grpc"
                flow.response.trailers = http.Headers([(b"grpc-status", b"0")])
                flow.response.headers.pop("content-length", None)
            elif not getattr(wire, "passthrough", False):
                flow.response.content = json_bytes(translated)
                flow.response.headers["content-type"] = "application/json"
            flow.metadata["client_payload"] = translated
            self._emit_response(flow, content, streaming=False)
        except Exception as exc:
            self._error(flow, "Response conversion failed: " + str(exc), 502,
                        code=ErrorCode.RESPONSE_CONVERSION_FAILED)

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
        route = flow.metadata["defuzex_resolved_route"]
        decoder = self.protocols.get(route.protocol_plugin, self.protocols["json-http"])
        payload = decoder.decode_response(
            content, flow.metadata.get("upstream_content_type", flow.response.headers.get("content-type", "")))
        emit("llm_response", **self._fields(flow),
             model=_model(payload) or flow.metadata.get("defuzex_target_model"),
             status=flow.metadata.get("upstream_status", flow.response.status_code),
             latency_ms=round((time.monotonic()-flow.metadata["defuzex_started"])*1000, 3),
             streaming=streaming, payload=redact(payload, self.secrets),
             client_payload=redact(flow.metadata.get("client_payload"), self.secrets),
             raw_body=redact(content.decode("utf-8", errors="replace"), self.secrets), truncated=False)

    def _emit_error(self, flow, message, *, code, local_status=None):
        '''According to issue 19, we need more bug report'''
        # A blocked request is only actionable if the event names what was blocked.

        metadata = flow.metadata
        tool = metadata.get("abb_tool", False)
        routed = metadata.get("defuzex_provider") is not None
        failure = InterceptionFailure(
            code=code, message=message, call_id=metadata["defuzex_call_id"],
            request_kind=RequestKind.TOOL if tool else (
                RequestKind.MODEL if metadata.get("defuzex_route") else RequestKind.UNKNOWN),
            source_host=metadata.get("defuzex_source_host"),
            source_port=metadata.get("defuzex_source_port"),
            source_path=metadata.get("defuzex_source_path"), method=flow.request.method,
            route_id=metadata.get("defuzex_route"), provider=metadata.get("defuzex_provider"),
            target_host=flow.request.pretty_host if routed or tool else None,
            target_port=flow.request.port if routed or tool else None,
            target_path=flow.request.path if routed or tool else None,
            local_status=local_status, upstream_status=metadata.get("upstream_status"),
        )
        # Preserve event names and tool fields consumed by existing trace readers.
        fields = self._tool_fields(flow) if tool else {}
        fields.update(failure_fields(failure, self.secrets))
        fields.update(agent_id=self.config.agent_id,
                      framework_span_id=metadata.get("framework_span_id"))
        emit("tool_error" if tool else "llm_error", **redact(fields, self.secrets))

    def _error(self, flow, message, status, *, code):
        self._emit_error(flow, message, code=code, local_status=status)
        flow.metadata.pop("wire", None)
        if flow.metadata.get("source_grpc"):
            from ..transport.grpc import status_code
            flow.response = http.Response.make(200, b"", {"content-type": "application/grpc",
                "grpc-status": str(status_code(status)), "grpc-message": quote(str(redact(message, self.secrets)))})
        else:
            flow.response = http.Response.make(status, json_bytes(_error_envelope(
                code, status, redact(message, self.secrets),
                upstream_status=flow.metadata.get("upstream_status", status))),
                                               {"content-type": "application/json"})

    def error(self, flow):
        capture = flow.metadata.pop("defuzex_capture", None)
        if capture:
            capture.close()
        if "defuzex_call_id" in flow.metadata:
            self._emit_error(flow, str(flow.error), code=ErrorCode.TRANSPORT_ERROR)
        # A transparent proxy must not turn an upstream transport failure into a
        # response. Left alone, mitmproxy answers the client with its own HTML 502
        # page (a response assigned in this hook is not sent), which a client can
        # only read as a malformed reply: the KUMA SDK classifies it as a
        # non-retryable invalid_response, and one dropped status poll ends a paid
        # run. Killing the flow closes the client connection without a response,
        # so the client sees the same transport failure a direct connection would
        # and applies its own retry policy.
        if flow.killable:
            flow.kill()

    def _route(self, flow):
        explicit = next((r for r in self.config.routes if self.policy.matches(r, flow.request)), None)
        return explicit if explicit is not None else self.automatic.resolve(flow.request)

    def _validate_plugins(self):
        missing = ({r.protocol_plugin for r in self.config.routes} - self.protocols.keys()
                   | {c.auth_plugin for c in self.config.credentials} - self.authentication.keys()
                   | {self.config.target.target_plugin} - self.targets.keys())
        if missing:
            raise RuntimeError("Unknown model interceptor plugins: " + ", ".join(sorted(missing)))


def _model(payload):
    return payload.get("model") if isinstance(payload, dict) else None


# Upstream answers that describe a passing condition rather than a decision.
_RETRYABLE_UPSTREAM_STATUSES = frozenset({408, 425, 429})


def _error_envelope(code, status, message, *, upstream_status=None):
    """Error body in the shape clients parse: string code and an explicit retry flag.

    A client reads ``code`` only when it is a string and treats a missing
    ``retryable`` as False. Policy, authentication, request preparation and
    response conversion failures are decisions and stay non-retryable; an
    upstream error is retryable only when its own status says the condition passes.
    """
    # A local 502 can also describe an error carried in a successful HTTP body;
    # it is not evidence that the actual upstream reported a transient failure.
    source_status = status if upstream_status is None else upstream_status
    retryable = code == ErrorCode.UPSTREAM_ERROR and (
        source_status in _RETRYABLE_UPSTREAM_STATUSES or source_status >= 500)
    return {"error": {"code": ErrorCode(code).value, "status": status,
                      "message": message, "retryable": retryable}}
