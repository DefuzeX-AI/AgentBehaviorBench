"""Issue #83: choose a compatible target without losing images or credentials."""
import json
import tempfile
import unittest
import struct
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from mitmproxy import http
from defuzex_model_interceptor.config import ServiceConfig, ServiceConfigurationError
from defuzex_model_interceptor.proxy.addon import ModelInterceptorAddon


class TargetRoutingTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.events = []
        capture = patch('defuzex_model_interceptor.observation.events.emit',
                        side_effect=lambda event, **data: self.events.append(dict(event=event, **data)))
        capture.start()
        self.addCleanup(capture.stop)
        self.data = dict(agent_id='fixture', max_trace_bytes=4096, mode='replace', routes=[],
                         credentials=[dict(id='source', auth_plugin='bearer-token',
                                           token_file=self.secret('source.token', 'source-run-token'))],
                         targets={}, target_rules=[])
        for name, model, endpoint, inputs in (
            ('chat', 'chat-model', '/chat/completions', ['text']),
            ('vision', 'vision-model', '/chat/completions', ['text', 'image']),
            ('vectors', 'vector-model', '/embeddings', ['text']),
        ):
            self.data['targets'][name] = dict(provider_id=name, target_plugin='compatible-json',
                base_url=f'https://{name}.example/v1', model=model, headers={},
                input_modalities=inputs, endpoint_paths={endpoint: endpoint},
                secret_file=self.secret(name + '.secret', name + '-upstream-secret'))
        for name, protocol, kind in (('chat', 'openai-chat', 'text'),
                                      ('vision', 'openai-chat', 'image'),
                                      ('vectors', 'openai-embeddings', 'text')):
            self.data['target_rules'].append(dict(id=name, target=name, protocols=[protocol], input=kind))

    def secret(self, filename, content):
        path = self.root / filename
        path.write_text(content)
        return str(path)

    def addon(self):
        path = self.root / 'config.json'
        path.write_text(json.dumps(self.data))
        return ModelInterceptorAddon(ServiceConfig.load(path))

    def request(self, path, body):
        return SimpleNamespace(metadata={}, response=None, request=http.Request.make(
            'POST', 'https://original.example/v1' + path, json.dumps(body).encode(),
            {'content-type': 'application/json', 'authorization': 'Bearer source-run-token'}))

    def test_one_agent_uses_three_targets_and_preserves_image_parts(self):
        images = [{'type': 'text', 'text': 'Compare these pictures'},
                  {'type': 'image_url', 'image_url': {'url': 'https://assets.example/one.png', 'detail': 'high'}},
                  {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,aW1hZ2U='}}]
        addon = self.addon()
        for target, path, body in (
            ('chat', '/chat/completions', {'messages': [{'role': 'user', 'content': 'Hello'}]}),
            ('vectors', '/embeddings', {'input': ['hello', 'world']}),
            ('vision', '/chat/completions', {'messages': [{'role': 'user', 'content': images}]}),
        ):
            with self.subTest(target=target):
                original = dict(body, model='original-model')
                call = self.request(path, original)
                addon.request(call)
                self.assertIsNone(call.response)
                self.assertEqual(call.request.host, target + '.example')
                self.assertEqual(call.request.headers['authorization'], 'Bearer ' + target + '-upstream-secret')
                self.assertEqual(json.loads(call.request.content), dict(original, model=self.data['targets'][target]['model']))
                call.response = http.Response.make(200, json.dumps(
                    {'data': [{'embedding': [0.1, 0.2]}]} if target == 'vectors' else
                    {'choices': [{'message': {'content': 'done'}}]}).encode(), {'content-type': 'application/json'})
                addon.response(call)
                self.assertEqual(self.events[-1]['target_id'], target)
                self.assertEqual(self.events[-1]['target_rule'], target)
        self.assertNotIn('upstream-secret', json.dumps(self.events))

    def test_missing_image_rule_never_sends_to_chat_target(self):
        self.data['target_rules'] = self.data['target_rules'][:1]
        call = self.request('/chat/completions', {'messages': [{'role': 'user', 'content': [
            {'type': 'image_url', 'image_url': {'url': 'https://assets.example/image.png'}}]}]})
        self.addon().request(call)
        self.assertEqual(call.response.status_code, 422)
        self.assertIn('No model target rule', call.response.text)
        self.assertEqual(call.request.host, 'original.example')
        self.assertNotIn('upstream-secret', str(call.request.headers))

    def test_legacy_target_does_not_rewrite_embeddings_or_undeclared_images(self):
        self.data['target'] = self.data['targets']['chat']
        self.data['target'].pop('endpoint_paths')
        self.data['credentials'][0]['secret_file'] = self.data['targets']['chat']['secret_file']
        del self.data['targets'], self.data['target_rules']
        addon = self.addon()
        call = self.request('/embeddings', {'model': 'embedding-model', 'input': 'hello'})
        addon.request(call)
        self.assertEqual(call.response.status_code, 422)
        self.assertIn('explicit target rule', call.response.text)
        image = self.request('/chat/completions', {'messages': [{'role': 'user', 'content': [
            {'type': 'image_url', 'image_url': {'url': 'https://assets.example/a.png'}}]}]})
        addon.request(image)
        self.assertEqual(image.response.status_code, 422)
        self.assertIn('does not support image input', image.response.text)

    def test_default_run_target_preserves_images_without_explicit_rules(self):
        self.data['target'] = dict(self.data['targets']['chat'], input_modalities=['text', 'image'])
        self.data['target'].pop('endpoint_paths')
        self.data['credentials'][0]['secret_file'] = self.data['target']['secret_file']
        del self.data['targets'], self.data['target_rules']
        parts = [{'type': 'text', 'text': 'Review the generated figure'},
                 {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,aW1hZ2U=', 'detail': 'high'}}]
        body = {'model': 'source-model', 'messages': [{'role': 'user', 'content': parts}]}
        call = self.request('/chat/completions', body)
        addon = self.addon()
        addon.request(call)
        self.assertIsNone(call.response)
        self.assertEqual(call.request.host, 'chat.example')
        self.assertEqual(call.request.headers['authorization'], 'Bearer chat-upstream-secret')
        self.assertEqual(json.loads(call.request.content), dict(body, model='chat-model'))
        # Unsupported remote model capabilities remain actual provider failures.
        failure = b'{"error":{"message":"selected model does not support image input"}}'
        call.response = http.Response.make(400, failure, {'content-type': 'application/json'})
        addon.response(call)
        self.assertEqual(call.response.status_code, 400)
        self.assertIn('selected model does not support image input', call.response.text)
        self.assertEqual(json.loads(call.response.content)['error']['code'], 'upstream_error')
        self.assertNotIn('upstream-secret', json.dumps(self.events))

    def test_gemini_inline_images_survive_rest_and_grpc_conversion(self):
        from google.ai.generativelanguage_v1beta.types import GenerateContentRequest
        self.data['credentials'].append(dict(id='google', auth_plugin='google-api-key',
            token_file=self.secret('google.token', 'google-run-token')))
        self.data['target_rules'][1]['protocols'] += ['gemini-content', 'gemini-grpc']
        body = {'contents': [{'role': 'user', 'parts': [
            {'text': 'Read the image'}, {'inlineData': {'mimeType': 'image/png', 'data': 'aW1hZ2U='}}]}]}
        addon = self.addon()
        for grpc in (False, True):
            with self.subTest(grpc=grpc):
                if grpc:
                    message = GenerateContentRequest(model='models/source', contents=[{'role': 'user', 'parts': [
                        {'text': 'Read the image'}, {'inline_data': {'mime_type': 'image/png', 'data': b'image'}}]}])
                    payload = GenerateContentRequest.serialize(message)
                    payload = struct.pack('>BI', 0, len(payload)) + payload
                    path = '/google.ai.generativelanguage.v1beta.GenerativeService/GenerateContent'
                else:
                    payload, path = json.dumps(body).encode(), '/v1beta/models/source:generateContent'
                call = SimpleNamespace(metadata={}, response=None, request=http.Request.make(
                    'POST', 'https://generativelanguage.googleapis.com' + path, payload,
                    {'content-type': 'application/grpc' if grpc else 'application/json',
                     'x-goog-api-key': 'google-run-token'}))
                addon.request(call)
                self.assertIsNone(call.response, call.response)
                self.assertEqual(call.request.host, 'vision.example')
                self.assertEqual(call.request.headers['authorization'], 'Bearer vision-upstream-secret')
                self.assertEqual(json.loads(call.request.content)['messages'][0]['content'], [
                    {'type': 'text', 'text': 'Read the image'},
                    {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,aW1hZ2U='}}])

    def test_native_responses_and_anthropic_images_are_preserved(self):
        self.data['targets']['vision']['endpoint_paths'].update({'/responses': '/responses', '/messages': '/messages'})
        self.data['target_rules'][1]['protocols'] += ['openai-responses', 'anthropic-messages']
        self.data['credentials'].append(dict(id='anthropic', auth_plugin='anthropic-api-key',
            token_file=self.secret('anthropic.token', 'anthropic-run-token')))
        addon = self.addon()
        for path, body in (
            ('/responses', {'input': [{'role': 'user', 'content': [
                {'type': 'input_text', 'text': 'Read'},
                {'type': 'input_image', 'image_url': 'https://assets.example/image.png'}]}]}),
            ('/messages', {'messages': [{'role': 'user', 'content': [
                {'type': 'text', 'text': 'Read'}, {'type': 'image', 'source': {
                    'type': 'base64', 'media_type': 'image/png', 'data': 'aW1hZ2U='}}]}]}),
        ):
            with self.subTest(path=path):
                call = self.request(path, body)
                if path == '/messages':
                    del call.request.headers['authorization']
                    call.request.headers['x-api-key'] = 'anthropic-run-token'
                addon.request(call)
                self.assertIsNone(call.response)
                self.assertEqual(json.loads(call.request.content), dict(body, model='vision-model'))

    def test_wrong_source_token_cannot_select_or_leak_target_credentials(self):
        call = self.request('/embeddings', {'input': 'hello'})
        call.request.headers['authorization'] = 'Bearer wrong'
        self.addon().request(call)
        self.assertEqual(call.response.status_code, 401)
        self.assertEqual(call.request.host, 'original.example')
        self.assertNotIn('upstream-secret', json.dumps(self.events) + str(call.request.headers))

    def test_unknown_multimodal_embedding_input_is_not_sent_to_text_target(self):
        call = self.request('/embeddings', {'input': [{'type': 'image_url', 'image_url': 'https://assets.example/a.png'}]})
        self.addon().request(call)
        self.assertEqual(call.response.status_code, 422)
        self.assertIn('Multimodal embeddings', call.response.text)

    def test_gemini_private_image_reference_is_not_silently_removed(self):
        self.data['credentials'].append(dict(id='google', auth_plugin='google-api-key',
            token_file=self.secret('google.token', 'google-run-token')))
        self.data['target_rules'][1]['protocols'].append('gemini-content')
        call = SimpleNamespace(metadata={}, response=None, request=http.Request.make('POST',
            'https://generativelanguage.googleapis.com/v1beta/models/source:generateContent',
            json.dumps({'contents': [{'parts': [{'fileData': {'mimeType': 'image/png', 'fileUri': 'gs://private/image'}}]}]}).encode(),
            {'content-type': 'application/json', 'x-goog-api-key': 'google-run-token'}))
        self.addon().request(call)
        self.assertEqual(call.response.status_code, 422)
        self.assertIn('private file references', call.response.text)
        self.assertEqual(call.request.host, 'generativelanguage.googleapis.com')

    def test_streaming_vision_keeps_selected_target_and_response_content(self):
        call = self.request('/chat/completions', {'stream': True, 'messages': [{'role': 'user', 'content': [
            {'type': 'image_url', 'image_url': {'url': 'https://assets.example/a.png'}}]}]})
        addon = self.addon()
        addon.request(call)
        call.response = http.Response.make(200, b'', {'content-type': 'text/event-stream'})
        addon.responseheaders(call)
        frames = b'data: {"choices":[{"delta":{"content":"red"}}]}\n\ndata: [DONE]\n\n'
        self.assertEqual(call.response.stream(frames), frames)
        call.response.stream(b'')
        self.assertEqual(self.events[-1]['target_id'], 'vision')
        self.assertTrue(self.events[-1]['streaming'])

    def test_ambiguous_rules_and_incompatible_capabilities_fail_at_startup(self):
        self.data['target_rules'].append(dict(id='duplicate', target='vision', protocols=['openai-chat'], input='text'))
        with self.assertRaisesRegex(ServiceConfigurationError, 'Ambiguous'):
            self.addon()
        self.data['target_rules'].pop()
        self.data['targets']['vision']['input_modalities'] = ['text']
        with self.assertRaisesRegex(ServiceConfigurationError, 'input modalities'):
            self.addon()

    def test_image_in_tool_result_uses_vision_but_tool_schema_does_not(self):
        self.data['targets']['vision']['endpoint_paths']['/messages'] = '/messages'
        self.data['target_rules'][1]['protocols'].append('anthropic-messages')
        self.data['credentials'].append(dict(id='anthropic', auth_plugin='anthropic-api-key',
            token_file=self.secret('anthropic.token', 'anthropic-run-token')))
        call = self.request('/messages', {'messages': [{'role': 'user', 'content': [
            {'type': 'tool_result', 'tool_use_id': 'tool-1', 'content': [
                {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/png', 'data': 'aW1hZ2U='}}]}]}]})
        call.request.headers['x-api-key'] = 'anthropic-run-token'
        del call.request.headers['authorization']
        addon = self.addon()
        addon.request(call)
        self.assertIsNone(call.response)
        self.assertEqual(call.request.host, 'vision.example')
        text = self.request('/chat/completions', {'messages': [{'role': 'user', 'content': 'hello'}],
            'tools': [{'type': 'function', 'function': {'name': 'image_url', 'description': 'Read an image'}}]})
        addon.request(text)
        self.assertEqual(text.request.host, 'chat.example')


if __name__ == '__main__':
    unittest.main()
