"""Proxy orchestration; per-call wire Strategies own protocol conversion."""
import asyncio
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
from ..routing.targets import ModelTargetRouter


from ..proxy.common import CommonInterceptor


class ReplaceInterceptor(CommonInterceptor):
    def __init__(self, config):
        super().__init__(config)
        self.protocols, self.authentication, self.targets = load_protocols(), load_authentication(), load_targets()
        self.credentials = {c.credential_id: c for c in config.credentials}
        self._validate_plugins()
        wires = load_wires()
        self.automatic = AutomaticModelRouter(wires, config.credentials, self.authentication)
        self.target_router = ModelTargetRouter(config, wires)
        from ..token_counting.service import TokenCountingService
        destinations = config.targets or {'default': config.target}
        self.token_counters = {name: TokenCountingService(config.token_counting, target.model)
                               for name, target in destinations.items()}

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
            # Validate source credentials before inspecting or selecting a destination.
            _authorize(authentication, outbound, credential.token, '')
            target, target_id, rule_id, operation, modality = self.target_router.select(route, flow.request)
            flow.metadata.update(target_id=target_id, target_rule=rule_id,
                                 model_operation=operation, input_modality=modality)
            reply = self.token_counters[target_id].handle(route.protocol_plugin, source_body)
            if reply is not None:
                self._local_count(flow, reply)
                return
            outbound = flow.request.copy()
            _authorize(authentication, outbound, credential.token, target.secret or credential.secret)
            prepared = self.targets[target.target_plugin].prepare_request(outbound, route=route, target=target)
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
        self._watch_upstream(flow)

    def _watch_upstream(self, flow):
        """Bound how long one upstream model call may stay silent (issue 444).

        Without this an upstream that accepts the request and never answers
        holds the Agent turn until the whole Case execution budget expires, and
        no event shows that a model call was pending.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:  # Direct hook calls outside mitmproxy's event loop.
            return
        flow.metadata["defuzex_activity"] = time.monotonic()
        flow.metadata["defuzex_watchdog"] = loop.create_task(self._upstream_watchdog(flow))

    async def _upstream_watchdog(self, flow):
        timeout = self.config.upstream_timeout_seconds
        while not flow.metadata.get("defuzex_settled"):
            delay = flow.metadata["defuzex_activity"] + timeout - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
                continue
            self._upstream_timed_out(flow, timeout)
            return

    def _upstream_timed_out(self, flow, timeout):
        flow.metadata.update(defuzex_settled=True, defuzex_timed_out=True)
        capture = flow.metadata.pop("defuzex_capture", None)
        if capture:
            capture.close()
        elapsed = time.monotonic() - flow.metadata["defuzex_started"]
        self._emit_error(flow, f"Upstream model response idle for {timeout:g} s "
                               f"(request pending {elapsed:.1f} s)", code=ErrorCode.TRANSPORT_ERROR)
        events.emit("llm_upstream_timeout", **self._fields(flow), timeout_seconds=timeout,
                    elapsed_ms=round(elapsed * 1000, 3),
                    response_started=flow.metadata.get("upstream_status") is not None,
                    chunks=flow.metadata.get("chunk_index", 0))
        # Close the client connection without a response, the same retryable
        # transport-failure shape CommonInterceptor.error uses (issue 68).
        # mitmproxy cannot kill a flow in transit, so cancel its connection handler.
        _close_client_connection(flow)

    def _settle(self, flow):
        flow.metadata["defuzex_settled"] = True
        watchdog = flow.metadata.pop("defuzex_watchdog", None)
        if watchdog is not None:
            watchdog.cancel()

    def error(self, flow):
        timed_out = flow.metadata.get("defuzex_timed_out")
        self._settle(flow)
        if timed_out:
            # The timeout already recorded this call; the cancelled connection
            # must not report it a second time.
            flow.metadata.pop("defuzex_call_id", None)
        super().error(flow)

    def responseheaders(self, flow):
        flow.metadata["defuzex_activity"] = time.monotonic()
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
        client_capture = (ResponseCapture(self.config.max_trace_bytes)
                          if getattr(wire, "capture_client_stream", False) else None)
        flow.metadata["defuzex_capture"] = capture
        flow.response.headers.pop("content-length", None)
        flow.response.headers.pop("content-encoding", None)
        if getattr(wire, "grpc", False):
            flow.response.headers["content-type"] = "application/grpc"
            flow.response.trailers = http.Headers()
        elif not getattr(wire, "passthrough", False):
            flow.response.headers["content-type"] = wire.stream_type

        def stream(chunk):
            flow.metadata["defuzex_activity"] = time.monotonic()
            if flow.metadata.get("defuzex_stream_failed") or flow.metadata.get("defuzex_timed_out"):
                return [] if chunk else b""
            try:
                if chunk:
                    capture.write(chunk)
                forwarded = converter.feed(chunk)
                if client_capture is not None and forwarded:
                    client_capture.write(forwarded)
                if forwarded:
                    flow.metadata["chunk_index"] += 1
                    events.emit("llm_chunk", agent_id=self.config.agent_id, call_id=flow.metadata["defuzex_call_id"],
                         sequence=flow.metadata["chunk_index"], upstream_bytes=len(chunk), client_bytes=len(forwarded),
                         elapsed_ms=round((time.monotonic()-flow.metadata["defuzex_started"])*1000, 3))
                if not chunk:
                    if client_capture is not None:
                        route = flow.metadata["defuzex_resolved_route"]
                        flow.metadata["client_payload"] = self.protocols[route.protocol_plugin].decode_response(
                            client_capture.finish(), wire.stream_type)
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
                if client_capture is not None:
                    client_capture.close()
                flow.metadata["defuzex_stream_emitted"] = True
                flow.metadata["defuzex_stream_failed"] = True
                self._emit_error(flow, str(exc), code=ErrorCode.STREAM_PROCESSING_FAILED)
                if getattr(wire, "grpc", False):
                    flow.response.trailers = http.Headers([(b"grpc-status", b"13"), (b"grpc-message", quote(str(redact(str(exc), self.secrets))).encode("ascii"))])
                    return [] if chunk else b""
                raise
        flow.response.stream = stream

    def response(self, flow):
        if flow.metadata.get("defuzex_timed_out"):
            return
        self._settle(flow)
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
            if status >= 400:
                self._emit_response(flow, content, streaming=False)
                self._error(flow, content.decode('utf-8', errors='replace') or f'Upstream HTTP {status}',
                            status, code=ErrorCode.UPSTREAM_ERROR)
            else:
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
        try:
            payload = decoder.decode_response(
                content, flow.metadata.get("upstream_content_type", flow.response.headers.get("content-type", "")))
        except (ValueError, UnicodeError):
            if flow.metadata.get('upstream_status', flow.response.status_code) < 400:
                raise
            payload = {'error': content.decode('utf-8', errors='replace')}
        events.emit("llm_response", **self._fields(flow),
             model=_model(payload) or flow.metadata.get("defuzex_target_model"),
             status=flow.metadata.get("upstream_status", flow.response.status_code),
             latency_ms=round((time.monotonic()-flow.metadata["defuzex_started"])*1000, 3),
             streaming=streaming, payload=redact(payload, self.secrets),
             response_adapter=getattr(flow.metadata.get("wire"), "response_adapter", None),
             client_payload=redact(flow.metadata.get("client_payload"), self.secrets),
             raw_body=redact(content.decode("utf-8", errors="replace"), self.secrets), truncated=False)

    def _route(self, flow):
        explicit = next((r for r in self.config.routes if self.policy.matches(r, flow.request)), None)
        return explicit if explicit is not None else self.automatic.resolve(flow.request)

    def _validate_plugins(self):
        destinations = tuple(self.config.targets.values()) or (self.config.target,)
        missing = ({r.protocol_plugin for r in self.config.routes} - self.protocols.keys()
                   | {c.auth_plugin for c in self.config.credentials} - self.authentication.keys()
                   | {t.target_plugin for t in destinations if t is not None} - self.targets.keys())
        if missing:
            raise RuntimeError("Unknown model interceptor plugins: " + ", ".join(sorted(missing)))


def _close_client_connection(flow):
    try:
        from mitmproxy import ctx
        handler = ctx.master.addons.get("proxyserver").connections[flow.client_conn.id]
        handler.transports[handler.client].handler.cancel("upstream model timeout")
    except (AttributeError, KeyError):  # Connection already closed.
        pass


def _model(payload):
    return payload.get('model') if isinstance(payload, dict) else None


def _authorize(plugin, request, token, secret):
    if hasattr(plugin, 'authorize_request'):
        plugin.authorize_request(request, temporary_token=token, upstream_secret=secret)
    else:
        plugin.authorize(request.headers, temporary_token=token, upstream_secret=secret)
