"""Observe authorized native traffic. Parsing evidence never rewrites a reply."""
import time
from uuid import uuid4
from urllib.parse import parse_qsl
from ..proxy.common import CommonInterceptor
from ..observation import events
from ..observation.capture import ResponseCapture
from ..registry import load_protocols, load_wires
from ..routing.automatic import AutomaticModelRouter
from ..error import ErrorCode, TargetRoutingError
from ..security.redaction import redact, _secret_key


class ObserveInterceptor(CommonInterceptor):
    def __init__(self, config):
        super().__init__(config)
        self.protocols = load_protocols()
        self.recognizer = AutomaticModelRouter(load_wires(), (), {})

    def request(self, flow):
        request = flow.request
        # Learn native values solely for redaction; do not authenticate or replace them.
        self._remember_secrets(request)
        span = request.headers.pop('x-abb-framework-span', None)
        flow.metadata.update(defuzex_call_id=f'call_{uuid4().hex}', defuzex_started=time.monotonic(),
            defuzex_source_host=request.pretty_host, defuzex_source_port=request.port,
            defuzex_source_path=request.path.split('?', 1)[0],
            source_grpc=request.headers.get('content-type', '').startswith('application/grpc'),
            framework_span_id=span if span and len(span) <= 64 else None)
        route = next((r for r in self.config.routes if self.policy.matches(r, request)), None)
        tool = next((r for r in self.config.tool_routes if self.policy.matches(r, request)), None)
        # A familiar API path does not authorize an arbitrary destination.
        if route is None and tool is None:
            if not self._hand_off_egress(flow):
                self._error(flow, 'Undeclared network request blocked', 403, code=ErrorCode.EGRESS_DENIED)
            return
        request.host = request.pretty_host.rstrip('.').lower()
        protocol = route.protocol_plugin if route else None
        if protocol is None and tool.purpose != 'evaluation':
            try:
                recognized = self.recognizer.recognize(request)
                protocol = recognized[0] if recognized else None
            except TargetRoutingError:
                protocol = None  # Preserve authorized bytes; classify as generic HTTP.
        if protocol:
            auxiliary = protocol in {'openai-input-tokens', 'anthropic-count-tokens'}
            flow.metadata.update(observe_protocol=protocol, observe_auxiliary=auxiliary,
                                 defuzex_route=route.route_id if route else 'observe:' + protocol)
            name = 'model_auxiliary_request' if auxiliary else 'llm_request'
        else:
            flow.metadata.update(abb_tool=True, purpose=tool.purpose, required=tool.required)
            name = 'tool_request'
        body = self._body(request)
        if protocol and not auxiliary:
            payload = body.get('payload')
            declared = payload.get('tools') if isinstance(payload, dict) else None
            names = []
            for item in declared if isinstance(declared, list) else []:
                function = item.get('function', {}) if isinstance(item, dict) else {}
                tool_name = item.get('name') if isinstance(item, dict) else None
                if not tool_name and isinstance(function, dict):
                    tool_name = function.get('name')
                names.append(tool_name)
            if names and all(isinstance(n, str) and n for n in names):
                signature = tuple(sorted(set(names)))
                for purpose, expected in self.config.observation_tool_purposes.items():
                    if signature == tuple(sorted(expected)):
                        flow.metadata['observation_purpose'] = purpose
        fields = self._tool_fields(flow) if flow.metadata.get('abb_tool') else self._fields(flow)
        events.emit(name, **fields, **body, source='native')

    def responseheaders(self, flow):
        if flow.response is None or 'defuzex_call_id' not in flow.metadata:
            return
        content_type = flow.response.headers.get('content-type', '').lower()
        if 'text/event-stream' not in content_type and 'application/grpc' not in content_type:
            return
        capture = ResponseCapture(self.config.max_trace_bytes)
        flow.metadata['defuzex_capture'] = capture
        def stream(chunk):
            if flow.metadata.get('observe_recorded'):
                return chunk
            try:
                if chunk:
                    capture.write(chunk)
                else:
                    self._record_response(flow, capture.finish())
                    flow.metadata['observe_recorded'] = True
            except Exception:
                capture.close()
                flow.metadata['observe_recorded'] = True
                self._capture_error(flow)
            return chunk  # No converter, framing change, synthetic SSE or error envelope.
        flow.response.stream = stream

    def response(self, flow):
        if (flow.response is None or flow.metadata.get('observe_recorded')
                or flow.metadata.get('observe_blocked')):
            return
        if flow.metadata.get('observe_protocol') or flow.metadata.get('abb_tool'):
            try:
                self._record_response(flow, flow.response.raw_content or b'')
            except Exception:
                self._capture_error(flow)

    def _record_response(self, flow, content):
        response = flow.response.copy()
        response.raw_content = content
        decoded = response.content or b''
        auxiliary = flow.metadata.get('observe_auxiliary')
        tool = flow.metadata.get('abb_tool')
        name = 'tool_response' if tool else 'model_auxiliary_response' if auxiliary else 'llm_response'
        body = self._body(response)
        protocol = self.protocols.get(flow.metadata.get('observe_protocol'))
        if protocol and not flow.metadata.get('source_grpc'):
            try:
                body['payload'] = redact(protocol.decode_response(decoded,
                    response.headers.get('content-type', '')), self.secrets)
            except Exception:
                # Raw evidence is still available. Parsing is not model execution.
                body['decode_status'] = 'unparsed'
        fields = self._tool_fields(flow) if tool else self._fields(flow)
        events.emit(name, **fields, **body, status=response.status_code, source='native',
                    latency_ms=round((time.monotonic()-flow.metadata['defuzex_started'])*1000, 3))

    def _capture_error(self, flow):
        # Fail evidence acceptance without substituting a response to the Agent.
        events.emit('observation_error', **self._fields(flow), error_code='capture_failed')

    def _fields(self, flow):
        fields = super()._fields(flow)
        fields['path'] = flow.request.path.split('?', 1)[0]
        for label, header in self.config.observation_headers.items():
            value = flow.request.headers.get(header)
            if value and len(value) <= 256 and all(ord(c) >= 32 for c in value):
                fields[label] = redact(value, self.secrets)
        if flow.metadata.get('observation_purpose'):
            fields['native_purpose'] = flow.metadata['observation_purpose']
            fields['purpose_evidence'] = 'declared_tool_set'
        return fields

    def _error(self, flow, message, status, *, code):
        flow.metadata['observe_blocked'] = True
        super()._error(flow, message, status, code=code)

    def error(self, flow):
        capture = flow.metadata.pop('defuzex_capture', None)
        if capture:
            capture.close()
        if 'defuzex_call_id' not in flow.metadata:
            return
        name = ('tool_error' if flow.metadata.get('abb_tool') else
                'model_auxiliary_error' if flow.metadata.get('observe_auxiliary') else 'llm_error')
        fields = self._tool_fields(flow) if flow.metadata.get('abb_tool') else self._fields(flow)
        events.emit(name, **fields, error_code='transport_error', source='native',
                    error=redact(str(flow.error), self.secrets))
        # Preserve a failed connection, rather than mitmproxy's synthetic HTML 502.
        if flow.killable:
            flow.kill()

    def _remember_secrets(self, request):
        values = []
        for key, value in request.headers.items():
            if _secret_key(key) or key.lower() in ('cookie', 'proxy-authorization'):
                values.append(value)
                if value.lower().startswith('bearer '):
                    values.append(value[7:])
                if key.lower() == 'cookie':
                    values.extend(part.partition('=')[2].strip() for part in value.split(';'))
        values.extend(v for k, v in parse_qsl(request.path.partition('?')[2]) if _secret_key(k))
        self.secrets = tuple(dict.fromkeys((*self.secrets, *(v for v in values if v))))
