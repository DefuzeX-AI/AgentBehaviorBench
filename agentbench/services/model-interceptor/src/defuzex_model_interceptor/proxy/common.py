"""Shared trace fields, redaction, egress policy and local failure reporting."""
import json
from urllib.parse import quote
from mitmproxy import http
from ..observation import events
from ..observation.events import failure_fields
from ..security.redaction import redact
from ..error import ErrorCode, InterceptionFailure, RequestKind
from ..transport.json import json_bytes
from ..routing.policy import EgressPolicy


class CommonInterceptor:
    def __init__(self, config):
        self.config = config
        self.policy = EgressPolicy(config)
        self.secrets = tuple(v for c in config.credentials for v in (c.token, c.secret))

    def running(self):
        events.emit("interceptor_ready", agent_id=self.config.agent_id, mode=self.config.mode)

    def _fields(self, flow):
        return dict(agent_id=self.config.agent_id, call_id=flow.metadata["defuzex_call_id"],
                    mode=self.config.mode, route_id=flow.metadata.get("defuzex_route"), method=flow.request.method,
                    source_host=flow.metadata.get("defuzex_source_host"),
                    source_path=flow.metadata.get("defuzex_source_path"), host=flow.request.pretty_host,
                    path=flow.request.path, provider=flow.metadata.get("defuzex_provider"),
                    framework_span_id=flow.metadata.get("framework_span_id"))

    def _tool_fields(self, flow):
        fields = self._fields(flow)
        # Query strings can carry credentials; retain the path and parsed body.
        fields['path'] = flow.request.path.split('?', 1)[0]
        fields['purpose'] = flow.metadata.get('purpose', 'tool')
        fields['required'] = flow.metadata.get('required', False)
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
        name = ('model_auxiliary_error' if getattr(metadata.get('wire'), 'auxiliary', False)
                else 'tool_error' if tool else 'llm_error')
        events.emit(name, **redact(fields, self.secrets))

    def _hand_off_egress(self, flow):
        """Send traffic that is neither a model nor a tool route to the egress observer.

        The observer decides, forwards and records it on its own event stream, so no
        model or tool event is emitted here and model trace acceptance never sees it.
        Returns False when no observer is configured, keeping the local denial.
        """
        proxy = self.config.egress_proxy
        if proxy is None:
            return False
        for key in ("defuzex_call_id", "defuzex_started"):
            flow.metadata.pop(key, None)
        flow.metadata["abb_egress"] = True
        # Bind the upstream to the requested name, not the transparent destination
        # IP, so the observer's allowlist judges the host that is actually contacted.
        flow.request.host = flow.request.pretty_host.rstrip(".").lower()
        flow.server_conn.via = ("http", proxy)
        return True

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
        # Handed-off egress is the exception: the observer already recorded the
        # decision, and mitmproxy's 502 names the refusal ("403 Forbidden") to the
        # Agent's tool instead of an unexplained reset.
        if flow.killable and not flow.metadata.get("abb_egress"):
            flow.kill()


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
