"""Local counting must preserve authentication, protocol shape and provenance."""
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from unittest.mock import patch
from mitmproxy import http
from test_auto_routing import config, flow
from defuzex_model_interceptor.config import Credential
from defuzex_model_interceptor.proxy.addon import ModelInterceptorAddon
from defuzex_model_interceptor.token_counting.service import TokenCountingService

OPTIONS = {'mode': 'local_estimate', 'models': {'test/model': 'o200k_base'}}
BODY = {'model': 'native-alias', 'input': [{'role': 'user', 'content': 'Hello 你好'}]}


class LocalCountingTest(unittest.TestCase):
    def setUp(self):
        self.events = []
        p = patch('defuzex_model_interceptor.proxy.addon.emit',
                  side_effect=lambda name, **data: self.events.append({'event': name, **data}))
        p.start()
        self.addCleanup(p.stop)

    def request(self, addon, body=BODY, token='openai-run-token'):
        request = flow('https://api.openai.com/v1/responses/input_tokens', json.dumps(body).encode(),
                       {'content-type': 'application/json', 'authorization': 'Bearer ' + token})
        addon.request(request)
        return request

    def test_local_count_never_routes_upstream_and_keeps_auth_secret_out(self):
        addon = ModelInterceptorAddon(replace(config(), token_counting=OPTIONS))
        with patch.object(addon.targets['openrouter'], 'prepare_request', side_effect=AssertionError('Network')):
            request = self.request(addon)
        self.assertEqual(request.response.status_code, 200)
        result = json.loads(request.response.content)
        self.assertEqual(result['object'], 'response.input_tokens')
        self.assertGreater(result['input_tokens'], 0)
        self.assertEqual(request.request.host, 'api.openai.com')
        self.assertNotIn('target-test-secret', str(request.request.headers))
        self.assertNotIn('target-test-secret', json.dumps(self.events))
        self.assertEqual([e['event'] for e in self.events], ['model_auxiliary_request', 'model_auxiliary_response'])
        evidence = self.events[-1]
        self.assertEqual(evidence['source'], 'local_estimate')
        self.assertEqual(evidence['model'], 'test/model')
        self.assertEqual(evidence['source_model'], 'native-alias')
        self.assertIn('structured-json-bpe-v1', evidence['algorithm'])
        self.assertEqual(len(evidence['request_sha256']), 64)

    def test_bad_auth_is_not_satisfied_by_local_response(self):
        request = self.request(ModelInterceptorAddon(replace(config(), token_counting=OPTIONS)), token='bad')
        self.assertEqual(request.response.status_code, 401)
        self.assertEqual(self.events[-1]['error_code'], 'authentication_failed')
        self.assertNotIn('model_auxiliary_response', [e['event'] for e in self.events])

    def test_messages_response_and_content_are_counted(self):
        credential = Credential('anthropic', 'anthropic-api-key', 'run-token', 'real-secret')
        settings = replace(config(), credentials=(credential,), token_counting=OPTIONS)
        addon = ModelInterceptorAddon(settings)
        request = flow('https://api.anthropic.com/v1/messages/count_tokens',
                       json.dumps({'model': 'native', 'messages': [{'role': 'user', 'content': '你好'}],
                                   'system': 'Be helpful'}).encode(),
                       {'content-type': 'application/json', 'x-api-key': 'run-token'})
        addon.request(request)
        self.assertEqual(request.response.status_code, 200)
        self.assertEqual(set(json.loads(request.response.content)), {'input_tokens'})

    def test_count_includes_new_turns_and_tool_schemas_not_previous_usage(self):
        service = TokenCountingService(OPTIONS, 'test/model')
        base = service.handle('openai-input-tokens', json.dumps(BODY).encode())
        expanded = dict(BODY, instructions='Work precisely', tools=[{'type': 'function', 'name': 'read',
                            'parameters': {'type': 'object', 'properties': {'path': {'type': 'string'}}}}])
        expanded['input'] = BODY['input'] + [{'role': 'assistant', 'content': 'A new turn ' * 30}]
        large = service.handle('openai-input-tokens', json.dumps(expanded).encode())
        self.assertGreater(large.body['input_tokens'], base.body['input_tokens'])
        self.assertEqual(large, service.handle('openai-input-tokens', json.dumps(expanded).encode()))

    def test_unknown_model_media_and_remote_state_explicitly_unsupported(self):
        for model, body in [('unknown', BODY), ('test/model', dict(BODY, previous_response_id='remote')),
            ('test/model', dict(BODY, input=[{'type': 'input_image', 'image_url': 'https://private/image'}])),
            ('test/model', dict(BODY, input=[{'type': 'reasoning', 'encrypted_content': 'secret'}]))]:
            with self.subTest(model=model, body=body):
                result = TokenCountingService(OPTIONS, model).handle('openai-input-tokens', json.dumps(body).encode())
                self.assertEqual(result.status, 404)
                self.assertNotIn('input_tokens', result.body)

    def test_malformed_oversized_and_special_token_text(self):
        service = TokenCountingService(dict(OPTIONS, max_input_bytes=1024), 'test/model')
        self.assertEqual(service.handle('openai-input-tokens', b'[]').status, 400)
        self.assertEqual(service.handle('openai-input-tokens', b'X' * 1025).status, 413)
        body = json.dumps(dict(BODY, input='<|endoftext|>')).encode()
        self.assertEqual(service.handle('openai-input-tokens', body).status, 200)

    def test_disabled_mode_preserves_actual_upstream_status_and_body(self):
        addon = ModelInterceptorAddon(config())
        request = self.request(addon)
        self.assertIsNone(request.response)
        self.assertEqual(request.request.host, 'target.example')
        request.response = http.Response.make(404, b'No such endpoint', {'content-type': 'text/plain'})
        addon.responseheaders(request)
        addon.response(request)
        self.assertEqual(request.response.content, b'No such endpoint')
        self.assertEqual(self.events[-1]['status'], 404)
        self.assertEqual([e['event'] for e in self.events], ['model_auxiliary_request', 'model_auxiliary_response'])

    def test_parallel_services_do_not_share_target_or_input(self):
        def run(i):
            model = f'model/{i}'
            service = TokenCountingService({'mode': 'local_estimate', 'models': {model: 'o200k_base'}}, model)
            return service.handle('openai-input-tokens', json.dumps(dict(BODY, input='x ' * (i + 1))).encode())
        with ThreadPoolExecutor(max_workers=4) as pool:
            replies = list(pool.map(run, range(8)))
        self.assertEqual([r.evidence['model'] for r in replies], [f'model/{i}' for i in range(8)])
        self.assertEqual(len({r.evidence['request_sha256'] for r in replies}), 8)

    def test_invalid_configuration_fails_before_network(self):
        for options in [{'mode': 'guess'}, {'mode': 'local_estimate', 'models': {'m': 'random'}},
                        {'unused': True}, {'max_input_bytes': True}]:
            with self.assertRaises(ValueError):
                TokenCountingService(options, 'm')


class NativeNetworkTest(unittest.TestCase):
    def test_native_review_verdict_and_401_are_never_replaced(self):
        from defuzex_model_interceptor.config import ToolRoute
        route = ToolRoute(('native.example',), (443,), ('POST',), ('/review',), 'content_safety', True)
        for status, payload in [(200, {'pass': False}), (401, {'message': 'token is required'})]:
            with self.subTest(status=status):
                events = []
                addon = ModelInterceptorAddon(replace(config(), tool_routes=(route,)))
                request = flow('https://native.example/review', b'{"scene":205,"content_text":"title"}',
                               {'content-type': 'application/json'})
                with patch('defuzex_model_interceptor.proxy.addon.emit',
                           side_effect=lambda name, **data: events.append({'event': name, **data})):
                    addon.request(request)
                    self.assertIsNone(request.response)
                    self.assertEqual(request.request.host, 'native.example')
                    original = json.dumps(payload).encode()
                    request.response = http.Response.make(status, original, {'content-type': 'application/json'})
                    addon.response(request)
                self.assertEqual(request.response.content, original)
                self.assertEqual(request.response.status_code, status)
                self.assertEqual(events[0]['payload']['scene'], 205)
                self.assertTrue(events[0]['required'])
                self.assertEqual(events[-1]['payload'], payload)

    def test_native_rule_does_not_allow_other_path_or_model_host(self):
        from defuzex_model_interceptor.config import ToolRoute
        route = ToolRoute(('native.example',), (443,), ('POST',), ('/review',), 'content_safety')
        addon = ModelInterceptorAddon(replace(config(), tool_routes=(route,)))
        with patch('defuzex_model_interceptor.proxy.addon.emit'):
            request = flow('https://native.example/private', b'{}', {'content-type': 'application/json'})
            addon.request(request)
        self.assertEqual(request.response.status_code, 403)
