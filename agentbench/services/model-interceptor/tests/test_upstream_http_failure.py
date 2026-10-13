"""A non-JSON HTTP failure is an upstream failure, not lost capture evidence."""
import json
import unittest
from unittest.mock import patch
from mitmproxy import http
from test_auto_routing import config, flow
from defuzex_model_interceptor.proxy.addon import ModelInterceptorAddon


class UpstreamHttpFailureTest(unittest.TestCase):
    def test_empty_and_html_502_keep_upstream_classification(self):
        for body in (b'', b'<html>Bad gateway</html>'):
            with self.subTest(body=body):
                events = []
                with patch('defuzex_model_interceptor.observation.events.emit',
                           side_effect=lambda name, **data: events.append((name, data))):
                    addon = ModelInterceptorAddon(config())
                    request = flow('https://api.openai.com/v1/chat/completions',
                        b'{"model":"test","messages":[{"role":"user","content":"hi"}]}',
                        {'content-type': 'application/json', 'authorization': 'Bearer openai-run-token'})
                    addon.request(request)
                    request.response = http.Response.make(502, body, {'content-type': 'text/html'})
                    addon.response(request)
                error = next(data for name, data in events if name == 'llm_error')
                self.assertEqual(error['error_code'], 'upstream_error')
                self.assertTrue(json.loads(request.response.content)['error']['retryable'])
                response = next(data for name, data in events if name == 'llm_response')
                self.assertEqual(response['raw_body'], body.decode())
                self.assertEqual(response['status'], 502)
