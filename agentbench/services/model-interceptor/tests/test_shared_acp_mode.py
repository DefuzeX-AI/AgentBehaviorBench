"""Exercise the real proxy handlers for both shared ACP modes."""
import json
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

from mitmproxy import http
from defuzex_model_interceptor.config import Credential, Route, ServiceConfig, Target, ToolRoute
from defuzex_model_interceptor.proxy.addon import ModelInterceptorAddon


class SharedACPModeTest(unittest.TestCase):
    def config(self, mode):
        return ServiceConfig(agent_id='fixture', mode=mode, max_trace_bytes=4096,
            target=Target('openrouter', 'openrouter', 'https://target.example/v1', 'chosen-model', {}),
            credentials=(Credential('shared', 'bearer-token', 'proxy-token', 'real-test-key'),) if mode == 'replace' else (),
            routes=(Route('shared-openai-chat', ('target.example',), (443,), ('POST',),
                          ('/v1/chat/completions',), 'openai-chat', 'shared' if mode == 'replace' else ''),),
            tool_routes=(ToolRoute(('target.example',), (443,), ('GET',), ('/v1/models',), 'metadata'),))

    def flow(self, method, path, token, body=b''):
        return SimpleNamespace(request=http.Request.make(method, 'https://target.example'+path, body,
            {'Authorization': 'Bearer '+token, 'content-type': 'application/json'}), response=None, metadata={})

    @patch('defuzex_model_interceptor.observation.events.emit')
    def test_request_replacement_and_native_observation(self, emit):
        for mode, key in [('replace', 'proxy-token'), ('observe', 'native-key')]:
            with self.subTest(mode=mode):
                proxy = ModelInterceptorAddon(self.config(mode))
                request = self.flow('POST', '/v1/chat/completions', key,
                    json.dumps({'model':'source-model', 'messages':[{'role':'user','content':'hello'}]}).encode())
                proxy.request(request)
                self.assertIsNone(request.response)
                self.assertEqual(request.request.headers['Authorization'],
                    'Bearer real-test-key' if mode == 'replace' else 'Bearer native-key')
                self.assertEqual(json.loads(request.request.content)['model'],
                    'chosen-model' if mode == 'replace' else 'source-model')
                request.response = http.Response.make(200, json.dumps({'choices':[
                    {'index':0,'message':{'role':'assistant','content':'hello back'},'finish_reason':'stop'}]}).encode(),
                    {'content-type':'application/json'})
                proxy.response(request)
                self.assertIn(b'hello back', request.response.content)
        self.assertNotIn('real-test-key', str(emit.call_args_list))

    @patch('defuzex_model_interceptor.observation.events.emit')
    def test_metadata_cannot_send_model_key_to_other_host(self, emit):
        config = replace(self.config('replace'), tool_routes=(
            ToolRoute(('other.example',), (443,), ('GET',), ('/v1/models',), 'metadata'),))
        proxy = ModelInterceptorAddon(config)
        request = self.flow('GET', '/v1/models', 'proxy-token')
        request.request.host = 'other.example'
        proxy.request(request)
        self.assertEqual(request.response.status_code, 401)
        self.assertEqual(request.request.headers['Authorization'], 'Bearer proxy-token')

    @patch('defuzex_model_interceptor.observation.events.emit')
    def test_metadata_authentication_and_bad_token(self, emit):
        proxy = ModelInterceptorAddon(self.config('replace'))
        request = self.flow('GET', '/v1/models', 'proxy-token')
        proxy.request(request)
        self.assertIsNone(request.response)
        self.assertEqual(request.request.headers['Authorization'], 'Bearer real-test-key')
        bad = self.flow('GET', '/v1/models', 'wrong-token')
        proxy.request(bad)
        self.assertEqual(bad.response.status_code, 401)
        self.assertNotIn('real-test-key', str(emit.call_args_list))
