"""Issue #444: a silent upstream model call is bounded and recorded.

Hooks run on a real asyncio loop with a short timeout; no network is used.
"""
import asyncio
import dataclasses
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mitmproxy import http
from test_auto_routing import config, flow
from defuzex_model_interceptor.config import ServiceConfig, ServiceConfigurationError
from defuzex_model_interceptor.proxy.addon import ModelInterceptorAddon

BODY = b'{"model":"test","messages":[{"role":"user","content":"hi"}]}'
HEADERS = {'content-type': 'application/json', 'authorization': 'Bearer openai-run-token'}


def model_flow():
    return flow('https://api.openai.com/v1/chat/completions', BODY, HEADERS)


class UpstreamTimeoutTest(unittest.TestCase):
    def run_hooks(self, scenario, timeout=0.05):
        events = []
        addon = ModelInterceptorAddon(dataclasses.replace(config(), upstream_timeout_seconds=timeout))
        with patch('defuzex_model_interceptor.observation.events.emit',
                   side_effect=lambda name, **data: events.append((name, data))), \
             patch('defuzex_model_interceptor.replace.handler._close_client_connection') as close:
            asyncio.run(scenario(addon))
        return events, close

    def test_silent_upstream_is_closed_and_recorded_once(self):
        request = model_flow()

        async def scenario(addon):
            addon.request(request)
            await asyncio.sleep(0.15)
            request.error = 'connection cancelled'
            request.killable = False
            addon.error(request)  # mitmproxy reports the cancelled connection.

        events, close = self.run_hooks(scenario)
        close.assert_called_once_with(request)
        names = [name for name, _ in events]
        self.assertEqual(names.count('llm_error'), 1)
        error = next(data for name, data in events if name == 'llm_error')
        self.assertEqual(error['error_code'], 'transport_error')
        timeout = next(data for name, data in events if name == 'llm_upstream_timeout')
        self.assertGreaterEqual(timeout['elapsed_ms'], 50)
        self.assertEqual(timeout['timeout_seconds'], 0.05)
        self.assertFalse(timeout['response_started'])
        self.assertEqual(timeout['call_id'], next(d for n, d in events if n == 'llm_request')['call_id'])

    def test_answer_before_timeout_cancels_watchdog(self):
        request = model_flow()

        async def scenario(addon):
            addon.request(request)
            request.response = http.Response.make(200, json.dumps({
                'model': 'test/model', 'choices': [{'message': {'role': 'assistant', 'content': 'ok'}}]}).encode(),
                {'content-type': 'application/json'})
            addon.responseheaders(request)
            addon.response(request)
            await asyncio.sleep(0.15)

        events, close = self.run_hooks(scenario)
        close.assert_not_called()
        self.assertNotIn('llm_upstream_timeout', [name for name, _ in events])

    def test_streamed_chunks_count_as_activity(self):
        request = model_flow()

        async def scenario(addon):
            addon.request(request)
            request.response = http.Response.make(200, b'', {'content-type': 'text/event-stream'})
            addon.responseheaders(request)
            for _ in range(4):
                await asyncio.sleep(0.03)
                request.response.stream(b': keep-alive\n\n')
            request.response.stream(b'data: [DONE]\n\n')
            request.response.stream(b'')
            addon.response(request)
            await asyncio.sleep(0.1)

        events, close = self.run_hooks(scenario, timeout=0.08)
        close.assert_not_called()
        self.assertNotIn('llm_upstream_timeout', [name for name, _ in events])

    def test_configuration_default_and_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            base = {'mode': 'observe', 'agent_id': 'a', 'max_trace_bytes': 4096}
            path.write_text(json.dumps(base))
            self.assertEqual(ServiceConfig.load(path).upstream_timeout_seconds, 300.0)
            path.write_text(json.dumps({**base, 'upstream_timeout_seconds': 12}))
            self.assertEqual(ServiceConfig.load(path).upstream_timeout_seconds, 12.0)
            for bad in (0, -1, True, 'x', None):
                path.write_text(json.dumps({**base, 'upstream_timeout_seconds': bad}))
                with self.subTest(bad=bad), self.assertRaises(ServiceConfigurationError):
                    ServiceConfig.load(path)


class SilentUpstreamProxyTest(unittest.TestCase):
    """Real mitmdump against a local HTTPS upstream that accepts and never answers."""

    def test_real_proxy_closes_the_client_connection(self):
        import datetime
        import http.client
        import os
        import socket
        import ssl
        import subprocess
        import threading
        import time
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import NameOID
        import ipaddress
        from defuzex_model_interceptor.proxy import addon

        release = threading.Event()

        class Silent(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'
            def log_message(self, *args):
                pass
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                release.wait(20)

        root = Path(tempfile.mkdtemp())
        key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, '127.0.0.1')])
        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
                .serial_number(1).not_valid_before(now).not_valid_after(now + datetime.timedelta(days=1))
                .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]),
                               critical=False).sign(key, hashes.SHA256()))
        (root / 'cert.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        (root / 'key.pem').write_bytes(key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        server = ThreadingHTTPServer(('127.0.0.1', 0), Silent)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(root / 'cert.pem', root / 'key.pem')
        server.socket = context.wrap_socket(server.socket, server_side=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.addCleanup(release.set)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        (root / 'token').write_text('run-token')
        (root / 'secret').write_text('target-secret')
        cfg = root / 'config.json'
        cfg.write_text(json.dumps({'agent_id': 'issue444', 'mode': 'replace', 'max_trace_bytes': 4096,
            'upstream_timeout_seconds': 1,
            'target': {'provider_id': 'openrouter', 'target_plugin': 'openrouter', 'headers': {},
                       'base_url': f'https://127.0.0.1:{server.server_port}/api/v1', 'model': 'test/model'},
            'credentials': [{'id': 'openai', 'auth_plugin': 'bearer-token', 'token_file': str(root / 'token'),
                             'secret_file': str(root / 'secret')}],
            'routes': [{'id': 'chat', 'host_patterns': ['127.0.0.1'], 'ports': [9], 'methods': ['POST'],
                        'path_patterns': ['/v1/chat/completions'], 'protocol_plugin': 'openai-chat',
                        'credential': 'openai'}]}))
        log_path = root / 'proxy.log'
        with log_path.open('w+') as log:
            process = subprocess.Popen(['mitmdump', '--quiet', '--mode', 'regular', '--listen-host', '127.0.0.1',
                '--listen-port', str(port), '--set', 'connection_strategy=lazy', '--set', 'ssl_insecure=true',
                '--set', 'confdir=' + str(root / 'ca'), '-s', str(Path(addon.__file__).with_name('loader.py'))],
                env={**os.environ, 'DEFUZEX_INTERCEPTOR_CONFIG': str(cfg)}, stdout=log, stderr=log)
            try:
                deadline = time.monotonic() + 15
                while True:
                    try:
                        with socket.create_connection(('127.0.0.1', port), timeout=.1):
                            break
                    except OSError:
                        if process.poll() is not None or time.monotonic() > deadline:
                            self.fail('Proxy did not start: ' + log_path.read_text())
                        time.sleep(.05)
                connection = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
                started = time.monotonic()
                connection.request('POST', 'http://127.0.0.1:9/v1/chat/completions', body=BODY,
                                   headers={'Content-Type': 'application/json', 'Authorization': 'Bearer run-token'})
                with self.assertRaises(http.client.RemoteDisconnected):
                    connection.getresponse()
                self.assertLess(time.monotonic() - started, 8)
                connection.close()
                time.sleep(.3)
            finally:
                release.set()
                process.terminate()
                process.wait(timeout=10)
        events = [json.loads(line.removeprefix('DEFUZEX_TRACE ')) for line in log_path.read_text().splitlines()
                  if line.startswith('DEFUZEX_TRACE ')]
        names = [event['event'] for event in events]
        self.assertEqual(names.count('llm_error'), 1, names)
        self.assertIn('llm_upstream_timeout', names)
        self.assertNotIn('target-secret', log_path.read_text())


if __name__ == '__main__':
    unittest.main()
