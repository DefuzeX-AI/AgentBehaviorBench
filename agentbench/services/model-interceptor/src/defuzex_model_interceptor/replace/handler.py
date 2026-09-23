"""Proxy orchestration; per-call wire Strategies own protocol conversion."""
import time
import json
from urllib.parse import quote
from uuid import uuid4
from mitmproxy import http
from ..observation import events
from ..security.redaction import redact
from ..error import ErrorCode, InterceptorAuthenticationError, TargetRoutingError
from ..registry import load_authentication, load_protocols, load_targets, load_wires
from ..observation.capture import ResponseCapture
from ..transport.json import json_bytes
from ..routing.automatic import AutomaticModelRouter


from ..proxy.common import CommonInterceptor


class ReplaceInterceptor(CommonInterceptor):
    def __init__(self, config):
        super().__init__(config)
        self.protocols, self.authentication, self.targets = load_protocols(), load_authentication(), load_targets()
        self.credentials = {c.credential_id: c for c in config.credentials}
        self._validate_plugins()
        self.automatic = AutomaticModelRouter(load_wires(), config.credentials, self.authentication)
        from ..token_counting.service import TokenCountingService
        self.token_counter = TokenCountingService(config.token_counting, config.target.model)

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
            flow.metadata.update(abb_tool=True, purpose=tool.purpose, required=tool.required)
            events.emit('tool_request', **self._tool_fields(flow), **self._body(flow.request))
            return
        if route is None:
            if not self._hand_off_egress(flow):
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
            reply = self.token_counter.handle(route.protocol_plugin, source_body)
            if reply is not None:
                self._local_count(flow, reply)
                return
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
        events.emit("model_auxiliary_request" if getattr(prepared.wire, 'auxiliary', False) else "llm_request",
             **self._fields(flow), source_model=prepared.source_model, model=prepared.target_model,
             source_payload=redact(prepared.source_payload, self.secrets), payload=redact(prepared.payload, self.secrets),
             source_raw_body=None if flow.metadata["source_grpc"] else redact(source_body.decode("utf-8", errors="replace"), self.secrets),
             source_transport="grpc" if flow.metadata["source_grpc"] else "http",
             raw_body=redact(flow.request.content.decode("utf-8"), self.secrets), truncated=False)

    def responseheaders(self, flow):
        wire = flow.metadata.get("wire")
        if wire is None or flow.response is None:
            return
        if getattr(wire, 'auxiliary', False):
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
                    events.emit("llm_chunk", agent_id=self.config.agent_id, call_id=flow.metadata["defuzex_call_id"],
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
            events.emit('tool_response', **self._tool_fields(flow), status=flow.response.status_code,
                 latency_ms=round((time.monotonic()-flow.metadata['defuzex_started'])*1000, 3),
                 **self._body(flow.response))
            return
        wire = flow.metadata.get("wire")
        if wire is None or flow.response is None or flow.metadata.get("defuzex_stream_emitted"):
            return
        if getattr(wire, 'auxiliary', False):
            events.emit('model_auxiliary_response', **self._fields(flow), status=flow.response.status_code,
                 **self._body(flow.response))
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

    def _local_count(self, flow, reply):
        """Reply locally only after authentication; never install real credentials."""
        events.emit('model_auxiliary_request', **self._fields(flow), operation='token_count',
             source='local_estimate', request_sha256=reply.evidence['request_sha256'],
             **self._body(flow.request))
        flow.response = http.Response.make(reply.status, json_bytes(reply.body),
            {'content-type': 'application/json', 'x-abb-token-count-source': 'local_estimate'})
        events.emit('model_auxiliary_response', **self._fields(flow), operation='token_count',
             status=reply.status, **reply.evidence, **self._body(flow.response))

    def _emit_response(self, flow, content, *, streaming):
        route = flow.metadata["defuzex_resolved_route"]
        decoder = self.protocols.get(route.protocol_plugin, self.protocols["json-http"])
        payload = decoder.decode_response(
            content, flow.metadata.get("upstream_content_type", flow.response.headers.get("content-type", "")))
        events.emit("llm_response", **self._fields(flow),
             model=_model(payload) or flow.metadata.get("defuzex_target_model"),
             status=flow.metadata.get("upstream_status", flow.response.status_code),
             latency_ms=round((time.monotonic()-flow.metadata["defuzex_started"])*1000, 3),
             streaming=streaming, payload=redact(payload, self.secrets),
             client_payload=redact(flow.metadata.get("client_payload"), self.secrets),
             raw_body=redact(content.decode("utf-8", errors="replace"), self.secrets), truncated=False)

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
    return payload.get('model') if isinstance(payload, dict) else None
