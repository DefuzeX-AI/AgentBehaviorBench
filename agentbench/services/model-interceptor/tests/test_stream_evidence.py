"""Replacement proxy saves native SSE frames before EOF without changing forwarding."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from mitmproxy import http
from test_auto_routing import config, flow
from defuzex_model_interceptor.proxy.addon import ModelInterceptorAddon
from defuzex_model_interceptor.observation.stream import StreamEvidence


class StreamEvidenceTests(unittest.TestCase):
    def test_split_utf8_and_multiple_sse_frames(self):
        frame = ('data: ' + json.dumps({'choices': [{'delta': {'content': '你好，España'}}]},
                                      ensure_ascii=False) + '\r\n\r\n').encode()
        evidence = StreamEvidence()
        frames = []
        for byte in frame + frame + b'data: [DONE]\r\n\r\n':
            frames.extend(evidence.feed(bytes([byte])))
        self.assertEqual([row['sequence'] for row in frames], [1, 2])
        self.assertEqual(frames[0]['payload']['choices'][0]['delta']['content'], '你好，España')
        self.assertEqual(evidence.feed(b''), [])

    def test_errors_and_incomplete_content_are_retained(self):
        evidence = StreamEvidence()
        self.assertEqual(evidence.feed(b'data: {"error":"failure"}\n\n')[0]['payload']['error'], 'failure')
        evidence.feed(b'data: {"partial":')
        self.assertIn('incomplete_sse_frame', evidence.feed(b'')[0]['payload'])

    def test_proxy_records_before_eof_and_disconnect_does_not_invent_response(self):
        events = []
        with patch('defuzex_model_interceptor.observation.events.emit',
                   side_effect=lambda name, **data: events.append({'event': name, **data})):
            addon = ModelInterceptorAddon(config())
            request = flow('https://api.openai.com/v1/chat/completions',
                b'{"model":"test","messages":[],"stream":true}',
                {'content-type': 'application/json', 'authorization': 'Bearer openai-run-token',
                 'x-abb-framework-span': 'model-span'})
            addon.request(request)
            request.response = http.Response.make(200, b'', {'content-type': 'text/event-stream'})
            addon.responseheaders(request)
            payload = {'choices': [{'delta': {'content': '你好，target-test-secret'}}]}
            raw = ('data: ' + json.dumps(payload, ensure_ascii=False) + '\n\n').encode()
            self.assertEqual(request.response.stream(raw), raw)
            delta = next(e for e in events if e['event'] == 'llm_delta')
            self.assertEqual(delta['call_id'], request.metadata['defuzex_call_id'])
            self.assertEqual(delta['framework_span_id'], 'model-span')
            self.assertEqual(delta['sequence'], 1)
            self.assertNotIn('target-test-secret', json.dumps(delta))
            self.assertIn('你好', delta['payload']['choices'][0]['delta']['content'])
            self.assertFalse(any(e['event'] == 'llm_response' for e in events))
            request.error = SimpleNamespace(msg='Client disconnected.')
            request.killable = False
            addon.error(request)
            self.assertEqual(sum(e['event'] == 'llm_delta' for e in events), 1)
            self.assertFalse(any(e['event'] == 'llm_response' for e in events))
            self.assertEqual(events[-1]['event'], 'llm_error')
            self.assertEqual(events[-1]['error_code'], 'transport_error')


if __name__ == '__main__':
    unittest.main()
