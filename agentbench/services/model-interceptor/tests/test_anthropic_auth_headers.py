import unittest
from model.anthropic.auth import AnthropicApiKeyAuthentication
from defuzex_model_interceptor.error import InterceptorAuthenticationError

class AnthropicAuthenticationTests(unittest.TestCase):
    def test_both_sdk_header_formats_keep_strict_token_validation(self):
        auth = AnthropicApiKeyAuthentication()
        for headers in ({'x-api-key': 'run-token'}, {'authorization': 'Bearer run-token'}):
            auth.authorize(headers, temporary_token='run-token', upstream_secret='upstream')
            self.assertEqual(headers['authorization'], 'Bearer upstream')
            self.assertNotIn('x-api-key', headers)
        for headers in ({}, {'authorization': 'Basic run-token'}, {'authorization': 'Bearer wrong'},
                        {'x-api-key': 'run-token', 'authorization': 'Bearer wrong'}):
            with self.assertRaises(InterceptorAuthenticationError):
                auth.authorize(headers, temporary_token='run-token', upstream_secret='upstream')
