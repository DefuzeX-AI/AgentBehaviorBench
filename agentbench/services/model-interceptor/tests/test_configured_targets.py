"""Configured targets reuse wire conversion and restrict supported endpoints."""
import json
import unittest
from types import SimpleNamespace

from defuzex_model_interceptor.config import Route, ServiceConfigurationError, Target, _target
from defuzex_model_interceptor.error import TargetRoutingError
from defuzex_model_interceptor.registry import load_targets


class ConfiguredTargetsTest(unittest.TestCase):
    def setUp(self):
        self.adapter = load_targets()['compatible-json']
        self.route = Route('test', ('source.example',), (443,), ('POST',),
                           ('/chat/completions',), 'openai-chat', 'key')
        self.payload = {'model': 'source-model', 'messages': [{'role': 'user', 'content': 'hello'}],
                        'tools': [{'type': 'function', 'function': {'name': 'read'}}], 'stream': True}
        self.request = SimpleNamespace(content=json.dumps(self.payload).encode(),
                                       headers={'authorization': 'Bearer test-secret'})

    def test_base_path_model_and_payload_are_preserved_for_custom_targets(self):
        target = Target('custom-provider', 'compatible-json', 'https://custom.example/api/v4',
                        'chosen-model', {}, {'/chat/completions': '/chat/completions'})
        result = self.adapter.prepare_request(self.request, route=self.route, target=target)
        self.assertEqual(self.request.host, 'custom.example')
        self.assertEqual(self.request.path, '/api/v4/chat/completions')
        self.assertEqual(result.provider_id, 'custom-provider')
        self.assertEqual(result.source_payload, self.payload)
        self.assertEqual(json.loads(self.request.content), {**self.payload, 'model': 'chosen-model'})
        self.assertEqual(self.request.headers['authorization'], 'Bearer test-secret')
        frame = b'data: {"choices":[{"delta":{"content":"reply"}}]}\n\n'
        stream = result.wire.stream()
        self.assertEqual(stream.feed(frame), frame)
        stream.feed(b'data: [DONE]\n\n')
        stream.feed(b'')

    def test_endpoint_mapping_uses_configuration_without_provider_branches(self):
        target = Target('custom-provider', 'compatible-json', 'https://custom.example',
                        'chosen', {}, {'/messages': '/custom/v1/messages'})
        self.route = Route('test', (), (), (), (), 'anthropic-messages', 'key')
        self.adapter.prepare_request(self.request, route=self.route, target=target)
        self.assertEqual(self.request.path, '/custom/v1/messages')

    def test_unsupported_endpoint_fails_before_request_mutation(self):
        target = Target('chat-only', 'compatible-json', 'https://custom.example',
                        'chosen', {}, {'/chat/completions': '/chat/completions'})
        original = self.request.content
        route = Route('test', (), (), (), (), 'openai-responses', 'key')
        with self.assertRaisesRegex(TargetRoutingError, 'does not support endpoint'):
            self.adapter.prepare_request(self.request, route=route, target=target)
        self.assertEqual(self.request.content, original)
        self.assertFalse(hasattr(self.request, 'host'))

    def test_service_config_validates_endpoint_paths(self):
        data = dict(provider_id='custom', target_plugin='compatible-json',
                    base_url='https://custom.example', model='chosen', headers={})
        self.assertIsNone(_target(data).endpoint_paths)
        self.assertEqual(_target({**data, 'endpoint_paths': {'/messages': '/anthropic/v1/messages'}})
                         .endpoint_paths['/messages'], '/anthropic/v1/messages')
        for mapping in ({}, [], {'/messages': 'https://other.example'}, {'/messages': '//other.example'},
                        {'/messages': '/../elsewhere'}, {'/messages': '/messages?key=secret'}):
            with self.subTest(mapping=mapping), self.assertRaises(ServiceConfigurationError):
                _target({**data, 'endpoint_paths': mapping})


if __name__ == '__main__':
    unittest.main()
