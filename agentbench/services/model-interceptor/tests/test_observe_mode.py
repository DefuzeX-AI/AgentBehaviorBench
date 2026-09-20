"""Native traffic stays native, including credentials, failures and streaming."""
import json
import gzip
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch
from mitmproxy import http
from test_auto_routing import config, flow
from defuzex_model_interceptor.config import ServiceConfig, Route, ToolRoute
from defuzex_model_interceptor.proxy.addon import ModelInterceptorAddon


def native_config(**options):
    routes = (Route('native', ('native.example',), (443,), ('POST',),
                    ('/v1/messages', '/v1/messages/count_tokens'), 'anthropic-messages', ''),)
    # Counting is a separate protocol, not a generation checkpoint.
    routes = (replace(routes[0], path_patterns=('/v1/messages',)),
              replace(routes[0], route_id='count', path_patterns=('/v1/messages/count_tokens',),
                      protocol_plugin='anthropic-count-tokens'))
    return replace(config(), mode='observe', target=None, credentials=(), routes=routes, **options)


class NativeObserveTest(unittest.TestCase):
    def setUp(self):
        self.events = []
        p = patch('defuzex_model_interceptor.observation.events.emit',
                  side_effect=lambda name, **data: self.events.append({'event': name, **data}))
        p.start(); self.addCleanup(p.stop)

    def request(self, addon, path='/v1/messages'):
        request = flow('https://native.example' + path,
            b'{ "model": "native-model", "messages": [], "tools": [{"defer_loading": true}] }',
            {'content-type': 'application/json', 'x-api-key': 'native-secret', 'anthropic-beta': 'native-beta'})
        original = request.request.copy()
        addon.request(request)
        self.assertIsNone(request.response)
        self.assertEqual(request.request.raw_content, original.raw_content)
        self.assertEqual(list(request.request.headers.items()), list(original.headers.items()))
        self.assertEqual(request.request.url, original.url)
        return request

    def test_no_target_no_surrogate_and_native_reply_unchanged(self):
        with patch('defuzex_model_interceptor.registry.load_targets', side_effect=AssertionError('replacement')):
            addon = ModelInterceptorAddon(native_config())
        request = self.request(addon)
        content = b'{ "content": [{"text":"native-secret"}], "usage": {"input_tokens":17} }'
        request.response = http.Response.make(200, content, {'content-type': 'application/json'})
        addon.response(request)
        self.assertEqual(request.response.raw_content, content)
        self.assertNotIn('native-secret', json.dumps(self.events))
        self.assertEqual(self.events[-1]['payload']['usage']['input_tokens'], 17)
        self.assertEqual(self.events[-1]['mode'], 'observe')
        self.assertEqual([e['event'] for e in self.events], ['llm_request', 'llm_response'])

    def test_native_401_429_and_non_json_errors_are_not_rewritten(self):
        for status in (401, 429, 503):
            with self.subTest(status=status):
                addon = ModelInterceptorAddon(native_config())
                request = self.request(addon)
                request.response = http.Response.make(status, b'raw upstream failure',
                                                      {'content-type': 'text/plain', 'retry-after': '12'})
                original = request.response.copy()
                addon.responseheaders(request); addon.response(request)
                self.assertEqual(request.response.raw_content, original.raw_content)
                self.assertEqual(request.response.status_code, status)
                self.assertEqual(list(request.response.headers.items()), list(original.headers.items()))
                self.assertEqual(self.events[-1]['status'], status)

    def test_stream_frames_headers_and_native_error_event_survive(self):
        addon = ModelInterceptorAddon(native_config())
        request = self.request(addon)
        request.response = http.Response.make(200, b'', {'content-type': 'text/event-stream', 'x-native': 'keep'})
        headers = list(request.response.headers.items())
        addon.responseheaders(request)
        chunks = [b'event: message_start\ndata: {"type":"message_start"}\n\n',
                  b'event: error\ndata: {"type":"error","error":{"message":"native error"}}\n\n', b'']
        self.assertEqual([request.response.stream(x) for x in chunks], chunks)
        addon.response(request)
        self.assertEqual(list(request.response.headers.items()), headers)
        responses = [e for e in self.events if e['event']=='llm_response']
        self.assertEqual(len(responses), 1)
        self.assertIn('native error', responses[0]['raw_body'])

    def test_token_count_stays_native_even_with_stale_local_options(self):
        addon = ModelInterceptorAddon(native_config(token_counting={'mode':'local_estimate'}))
        request = self.request(addon, '/v1/messages/count_tokens')
        request.response = http.Response.make(200, b'{"input_tokens":123}', {'content-type':'application/json'})
        addon.response(request)
        self.assertEqual(json.loads(request.response.content), {'input_tokens':123})
        self.assertEqual([e['event'] for e in self.events], ['model_auxiliary_request','model_auxiliary_response'])
        self.assertEqual(self.events[-1]['source'], 'native')

    def test_compressed_stream_is_decoded_only_for_redacted_evidence(self):
        addon = ModelInterceptorAddon(native_config())
        request = self.request(addon)
        content = b'data: {"type":"message_stop","text":"native-secret"}\n\n'
        wire = gzip.compress(content)
        request.response = http.Response.make(200, b'', {'content-type': 'text/event-stream',
                                                       'content-encoding': 'gzip'})
        addon.responseheaders(request)
        self.assertEqual(request.response.stream(wire), wire)
        request.response.stream(b'')
        self.assertEqual(request.response.headers['content-encoding'], 'gzip')
        self.assertIn('message_stop', self.events[-1]['raw_body'])
        self.assertNotIn('native-secret', json.dumps(self.events))

    def test_recognition_never_authorizes_an_unknown_host(self):
        addon = ModelInterceptorAddon(native_config())
        request = flow('https://unknown.example/v1/messages', b'{}', {'content-type':'application/json'})
        addon.request(request)
        self.assertEqual(request.response.status_code, 403)
        self.assertEqual(self.events[-1]['error_code'], 'egress_denied')

    def test_optional_native_review_is_recorded_without_synthetic_pass(self):
        rule = ToolRoute(('native.example',),(443,),('POST',),('/review',),'content_safety')
        addon = ModelInterceptorAddon(native_config(tool_routes=(rule,)))
        request = flow('https://native.example/review',b'{"scene":205}',{'content-type':'application/json'})
        addon.request(request)
        request.response=http.Response.make(401,b'{"message":"token is required"}',{'content-type':'application/json'})
        addon.response(request)
        self.assertEqual(self.events[-1]['event'],'tool_response')
        self.assertEqual(self.events[-1]['status'],401)
        self.assertFalse(self.events[-1]['required'])

    def test_capture_failure_does_not_change_delivered_stream(self):
        addon=ModelInterceptorAddon(native_config()); request=self.request(addon)
        request.response=http.Response.make(200,b'',{'content-type':'text/event-stream'})
        addon.responseheaders(request)
        with patch.object(request.metadata['defuzex_capture'],'write',side_effect=OSError('disk')):
            self.assertEqual(request.response.stream(b'data: native\n\n'),b'data: native\n\n')
            self.assertEqual(request.response.stream(b'data: next\n\n'),b'data: next\n\n')
            self.assertEqual(request.response.stream(b''),b'')
        self.assertEqual(self.events[-1]['event'],'observation_error')
        self.assertEqual(sum(e['event']=='observation_error' for e in self.events), 1)

    def test_failed_connection_does_not_turn_into_a_synthetic_http_reply(self):
        addon = ModelInterceptorAddon(native_config())
        request = self.request(addon)
        request.error = 'native connection failed'
        request.killable = True
        request.kill = Mock()
        addon.error(request)
        request.kill.assert_called_once()
        self.assertIsNone(request.response)
        self.assertEqual(self.events[-1]['error_code'], 'transport_error')

    def test_observe_config_does_not_load_replacement_secret_files(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'config.json'
            p.write_text(json.dumps({'agent_id':'native','mode':'observe','max_trace_bytes':4096,
                'credentials':[{'secret_file':'/absent','token_file':'/absent'}],
                'routes':[{'id':'native','host_patterns':['native.example'],'ports':[443],
                    'methods':['POST'],'path_patterns':['/v1/messages'],'protocol_plugin':'anthropic-messages'}]}))
            parsed=ServiceConfig.load(p)
            self.assertIsNone(parsed.target)
            self.assertEqual(parsed.credentials,())
            self.assertEqual(parsed.mode,'observe')

    def test_two_modes_do_not_share_mutations_or_event_sources(self):
        observe=ModelInterceptorAddon(native_config())
        replacement=ModelInterceptorAddon(config())
        native=self.request(observe)
        other=flow('https://source.example/v1/chat/completions',b'{"model":"original","messages":[]}',
            {'content-type':'application/json','authorization':'Bearer openai-run-token'})
        replacement.request(other)
        self.assertEqual(other.request.host,'target.example')
        self.assertEqual(native.request.host,'native.example')
        self.assertEqual([e['mode'] for e in self.events if e['event']=='llm_request'],['observe','replace'])

class NativeMetadataTest(unittest.TestCase):
    def test_session_header_is_observed_without_mutating_native_request(self):
        events = []
        addon = ModelInterceptorAddon(native_config(observation_headers={'native_session_id':'X-Mavis-Session-Id'}))
        request = flow('https://native.example/v1/messages', b'{"model":"native","messages":[]}',
                       {'content-type':'application/json','X-Mavis-Session-Id':'native-session'})
        headers = list(request.request.headers.items())
        with patch('defuzex_model_interceptor.observation.events.emit', side_effect=lambda name, **data:events.append(data)):
            addon.request(request)
        self.assertEqual(events[0]['native_session_id'],'native-session')
        self.assertEqual(list(request.request.headers.items()),headers)

    def test_credentials_cannot_be_selected_as_metadata(self):
        from defuzex_model_interceptor.config import _observation_headers, ServiceConfigurationError
        for header in ('Authorization','x-api-key','Cookie','x-access-token'):
            with self.assertRaises(ServiceConfigurationError):
                _observation_headers({'native_session_id':header})
