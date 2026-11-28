"""Gateway permission, credential substitution, protocols, and response regression checks."""
import io
import json
import unittest
from email.message import Message
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from uuid import UUID

from mitmproxy import http
from defuzex_model_interceptor.config import Target, Route, Credential, ServiceConfig
from defuzex_model_interceptor.defuze_server.access import check, AccessError, MAX_BYTES
from defuzex_model_interceptor.defuze_server.config import ENDPOINTS
from defuzex_model_interceptor.proxy.startup import preflight_targets
from defuzex_model_interceptor.proxy.addon import ModelInterceptorAddon


def target():
    return Target('defuze_server', 'defuze_server',
        'https://gateway.test/api/sdk/models/deepseek', 'deepseek-flash', {},
        endpoint_paths={p: p for p in ENDPOINTS})


class Reply(io.BytesIO):
    status = 200
    def __init__(self, body):
        super().__init__(body)
        self.headers = Message()
        self.headers['allow'] = 'POST, OPTIONS'
        self.headers['content-type'] = 'application/json'


class DefuzeTest(unittest.TestCase):
    def test_permission_is_options_and_bounded(self):
        reply = Reply(json.dumps({'name': 'Sdk Agent Model', 'parses': ['application/json']}).encode())
        opener = Mock(); opener.open.return_value = reply
        check(target().base_url, 'private-key', opener=opener)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.method, 'OPTIONS')
        self.assertIsNone(request.data)
        self.assertEqual(request.get_header('Authorization'), 'Bearer private-key')
        for body in (b'{}', b'not-json', b'x' * (MAX_BYTES + 1)):
            opener.open.return_value = Reply(body)
            with self.assertRaises(AccessError):
                check(target().base_url, 'private-key', opener=opener)

    def test_denial_does_not_expose_response_or_key(self):
        for status, code in ((401, 'unauthenticated'), (403, 'forbidden'), (302, 'http_302')):
            opener = Mock()
            opener.open.side_effect = HTTPError('https://private', status, 'private-key', {}, io.BytesIO(b'private-key'))
            with self.assertRaises(AccessError) as error:
                check(target().base_url, 'private-key', opener=opener)
            self.assertEqual(error.exception.code, code)
            self.assertNotIn('private-key', str(error.exception))

    def config(self, protocol='openai-chat'):
        return ServiceConfig('fixture', 4096, target(),
            (Credential('shared', 'anthropic-api-key' if protocol == 'anthropic-messages' else 'bearer-token',
                        'temporary', 'private-key'),),
            (Route('source', ('source.test',), (443,), ('POST',), ('/invoke',), protocol, 'shared'),))

    def test_preflight_failure_prevents_startup(self):
        with patch('defuzex_model_interceptor.defuze_server.access.check', side_effect=AccessError('forbidden')):
            with self.assertRaises(AccessError):
                preflight_targets(self.config())

    def test_protocols_forward_and_responses_remain_native(self):
        for protocol, endpoint in (('openai-chat', '/chat/completions'),
                                   ('openai-responses', '/responses'), ('anthropic-messages', '/messages')):
            events = []
            with patch('defuzex_model_interceptor.observation.events.emit',
                       side_effect=lambda event, **data: events.append((event, data))):
                addon = ModelInterceptorAddon(self.config(protocol))
                flow = SimpleNamespace(request=http.Request.make('POST', 'https://source.test/invoke',
                    json.dumps({'model': 'client-model', 'messages': [], 'input': 'hello'}).encode(),
                    {'content-type': 'application/json', 'authorization': 'Bearer temporary'}),
                    response=None, metadata={})
                addon.request(flow)
                self.assertIsNone(flow.response)
                self.assertEqual(flow.request.host, 'gateway.test')
                self.assertTrue(flow.request.path.endswith('/sdk/models/deepseek' + endpoint))
                self.assertEqual(flow.request.headers['authorization'], 'Bearer private-key')
                UUID(flow.request.headers['Idempotency-Key'])
                self.assertEqual(json.loads(flow.request.content)['model'], 'deepseek-flash')
                flow.response = http.Response.make(200, b'{"model":"deepseek-flash","choices":[]}',
                                                   {'content-type': 'application/json'})
                addon.response(flow)
                self.assertEqual(flow.response.status_code, 200)
                self.assertNotIn('private-key', json.dumps(events))

    def test_stream_tool_calls_and_usage_are_preserved(self):
        with patch('defuzex_model_interceptor.observation.events.emit'):
            addon = ModelInterceptorAddon(self.config())
            flow = SimpleNamespace(request=http.Request.make('POST', 'https://source.test/invoke',
                b'{"model":"client","messages":[],"stream":true}',
                {'content-type': 'application/json', 'authorization': 'Bearer temporary'}), response=None, metadata={})
            addon.request(flow)
            flow.response = http.Response.make(200, b'', {'content-type': 'text/event-stream'})
            addon.responseheaders(flow)
            raw = (b'data: {"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"id":"t",'
                   b'"type":"function","function":{"name":"echo","arguments":"{}"}}]},"finish_reason":"tool_calls"}]}\n\n'
                   b'data: {"choices":[],"usage":{"prompt_tokens":3,"completion_tokens":2,"total_tokens":5}}\n\n'
                   b'data: [DONE]\n\n')
            self.assertEqual(flow.response.stream(raw), raw)
            self.assertEqual(flow.response.stream(b''), b'')


if __name__ == '__main__':
    unittest.main()
