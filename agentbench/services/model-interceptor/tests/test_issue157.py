"""Completed native SSE responses survive a client's early disconnect."""
import gzip
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from mitmproxy import http
from defuzex_model_interceptor.config import Route, ServiceConfig, ToolRoute
from defuzex_model_interceptor.proxy.addon import ModelInterceptorAddon


def event(value):
    return b'data: ' + json.dumps(value).encode() + b'\n\n'


CHAT = (event({'choices': [{'index': 0, 'delta': {'reasoning_content': 'Think.',
        'content': 'hello', 'tool_calls': [{'index': 0, 'id': 'call_1', 'type': 'function',
        'function': {'name': 'shell', 'arguments': '{"cmd":"ls"}'}}]}, 'finish_reason': None}]}),
        event({'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'tool_calls'}]}),
        event({'choices': [], 'usage': {'prompt_tokens': 7, 'completion_tokens': 3, 'total_tokens': 10}}),
        b'data: [DONE]\n\n')
CANCEL = 'stream reset by client (CANCEL)'


class CompletedObserveStreamTest(unittest.TestCase):
    def setUp(self):
        self.events = []
        emitter = patch('defuzex_model_interceptor.observation.events.emit',
                        side_effect=lambda name, **data: self.events.append({'event': name, **data}))
        emitter.start()
        self.addCleanup(emitter.stop)

    def start(self, protocol='openai-chat', *, headers=None, status=200, tool=False):
        route = Route('native', ('native.example',), (443,), ('POST',), ('/stream',), protocol, '')
        config = ServiceConfig(agent_id='fixture', max_trace_bytes=16, target=None, credentials=(),
            routes=() if tool else (route,), mode='observe',
            tool_routes=(ToolRoute(('native.example',), (443,), ('POST',), ('/stream',)),) if tool else ())
        addon = ModelInterceptorAddon(config)
        flow = SimpleNamespace(request=http.Request.make('POST', 'https://native.example/stream',
            b'{"model":"native","stream":true,"messages":[]}',
            {'content-type': 'application/json', 'authorization': 'Bearer native-secret'}),
            response=None, metadata={}, error=None, killable=True, kill=Mock())
        addon.request(flow)
        flow.response = http.Response.make(status, b'', headers or {'content-type': 'text/event-stream'})
        addon.responseheaders(flow)
        return addon, flow, flow.metadata['defuzex_capture']

    def deliver(self, flow, chunks):
        headers = list(flow.response.headers.items())
        self.assertEqual([flow.response.stream(chunk) for chunk in chunks], list(chunks))
        self.assertEqual(list(flow.response.headers.items()), headers)

    def disconnect(self, addon, flow, error=CANCEL):
        flow.error = error
        addon.error(flow)

    def assert_response(self, raw, *, early=True):
        self.assertEqual([e['event'] for e in self.events], ['llm_request', 'llm_response'])
        response = self.events[-1]
        self.assertEqual(response['raw_body'], raw.decode())
        self.assertEqual(response['source'], 'native')
        self.assertEqual(response.get('client_closed_early', False), early)
        self.assertFalse(response['truncated'])
        return response

    def test_completed_chat_preserves_reasoning_tools_finish_and_usage(self):
        for error in (CANCEL, 'Client disconnected.'):
            with self.subTest(error=error):
                self.events.clear()
                addon, flow, capture = self.start()
                self.deliver(flow, CHAT)
                self.disconnect(addon, flow, error)
                response = self.assert_response(b''.join(CHAT))
                self.assertEqual(response['payload']['events'], [json.loads(chunk[6:]) for chunk in CHAT[:-1]])
                self.assertEqual(response['payload']['events'][-1]['usage']['total_tokens'], 10)
                self.assertTrue(capture._file.closed)
                flow.kill.assert_called_once()

    def test_normal_eof_and_late_callbacks_emit_only_one_response(self):
        addon, flow, capture = self.start()
        self.deliver(flow, CHAT)
        self.assertEqual(flow.response.stream(b''), b'')
        addon.response(flow)
        self.disconnect(addon, flow)
        addon.response(flow)
        self.assert_response(b''.join(CHAT), early=False)
        self.assertTrue(capture._file.closed)

    def test_error_then_eof_response_and_second_error_are_idempotent(self):
        addon, flow, capture = self.start()
        self.deliver(flow, CHAT)
        self.disconnect(addon, flow)
        flow.response.stream(b'')
        addon.response(flow)
        self.disconnect(addon, flow)
        self.assert_response(b''.join(CHAT))
        self.assertTrue(capture._file.closed)

    def test_response_hook_without_empty_chunk_uses_capture(self):
        addon, flow, capture = self.start()
        self.deliver(flow, CHAT)
        addon.response(flow)
        addon.response(flow)
        self.assert_response(b''.join(CHAT), early=False)
        self.assertTrue(capture._file.closed)

    def test_compressed_fragmented_and_crlf_streams(self):
        raw = b''.join(CHAT)
        for compressed in (False, True):
            with self.subTest(compressed=compressed):
                self.events.clear()
                raw_crlf = raw.replace(b'\n', b'\r\n')
                wire = gzip.compress(raw_crlf) if compressed else raw_crlf
                headers = {'content-type': 'text/event-stream;charset=UTF-8'}
                if compressed:
                    headers['content-encoding'] = 'gzip'
                addon, flow, capture = self.start(headers=headers)
                self.deliver(flow, [wire[i:i+1] for i in range(len(wire))])
                self.disconnect(addon, flow)
                self.assert_response(raw_crlf)
                self.assertTrue(capture._file.closed)

    def test_protocol_owned_terminal_events(self):
        for protocol, terminal in (('anthropic-messages', 'message_stop'),
                                   ('openai-responses', 'response.completed'),
                                   ('openai-chat-thinking', 'done')):
            with self.subTest(protocol=protocol):
                self.events.clear()
                raw = b'data: [DONE]\n\n' if terminal == 'done' else event({'type': terminal})
                addon, flow, _ = self.start(protocol)
                self.deliver(flow, [raw])
                self.disconnect(addon, flow)
                self.assert_response(raw)

    def test_unfinished_invalid_and_upstream_error_streams_stay_errors(self):
        invalid = [CHAT[:-1], (), (event({'type': 'done'}),), (b'data: [DONE]',), (event({'content': '[DONE]'}),),
                   (b'data: {bad json}\n\n', CHAT[-1]),
                   (event({'error': {'message': 'failed'}}), CHAT[-1]),
                   (*CHAT, event({'unexpected': 'after done'})),
                   (*CHAT, b'data: {"unfinished":'), (CHAT[-1][:-1],)]
        for chunks in invalid:
            with self.subTest(chunks=chunks):
                self.events.clear()
                addon, flow, capture = self.start()
                self.deliver(flow, chunks)
                self.disconnect(addon, flow)
                addon.response(flow)
                self.assertEqual([e['event'] for e in self.events], ['llm_request', 'llm_error'])
                self.assertEqual(self.events[-1]['error_code'], 'transport_error')
                self.assertTrue(capture._file.closed)

    def test_wrong_or_unknown_protocol_and_tool_stream_do_not_claim_completion(self):
        for protocol, tool in (('anthropic-messages', False), ('json-http', False), ('json-http', True)):
            with self.subTest(protocol=protocol, tool=tool):
                self.events.clear()
                addon, flow, _ = self.start(protocol, tool=tool)
                self.deliver(flow, CHAT)
                self.disconnect(addon, flow)
                self.assertEqual(self.events[-1]['event'], 'tool_error' if tool else 'llm_error')

    def test_server_failure_is_not_labelled_client_disconnect(self):
        addon, flow, _ = self.start()
        self.deliver(flow, CHAT)
        self.disconnect(addon, flow, 'Server disconnected.')
        self.assertEqual(self.events[-1]['event'], 'llm_error')

    def test_redaction_survives_recovered_response(self):
        addon, flow, _ = self.start()
        self.deliver(flow, [event({'choices': [{'delta': {'content': 'native-secret'}}]}), CHAT[-1]])
        self.disconnect(addon, flow)
        self.assertEqual(self.events[-1]['event'], 'llm_response')
        self.assertNotIn('native-secret', json.dumps(self.events))

    def test_capture_read_failure_is_visible_and_never_retried(self):
        addon, flow, capture = self.start()
        self.deliver(flow, CHAT)
        with patch.object(capture, 'finish', side_effect=OSError('disk')):
            self.disconnect(addon, flow)
        self.disconnect(addon, flow)
        flow.response.stream(b'')
        self.assertEqual([e['event'] for e in self.events], ['llm_request', 'observation_error'])
        self.assertTrue(capture._file.closed)

    def test_capture_write_failure_remains_single_evidence_failure(self):
        addon, flow, capture = self.start()
        with patch.object(capture, 'write', side_effect=OSError('disk')):
            self.deliver(flow, CHAT)
        self.disconnect(addon, flow)
        self.assertEqual([e['event'] for e in self.events], ['llm_request', 'observation_error'])
        self.assertTrue(capture._file.closed)
