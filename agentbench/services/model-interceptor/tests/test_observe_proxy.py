"""Exercise the production addon in mitmdump against a loopback native service."""
import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from defuzex_model_interceptor.proxy import addon


class NativeProxyTest(unittest.TestCase):
    def test_native_errors_streaming_and_credentials_through_real_proxy(self):
        received = []
        stream = b'event: message_stop\ndata: {"type":"message_stop"}\n\n'

        class Upstream(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers['Content-Length']))
                received.append((self.path, self.headers['Authorization'], body))
                status = int(self.path.rsplit('/', 1)[-1])
                reply = stream if status == 200 else b'{"error":"native-secret"}'
                self.send_response(status)
                self.send_header('Content-Type', 'text/event-stream' if status == 200 else 'application/json')
                self.send_header('Content-Length', str(len(reply)))
                self.send_header('Retry-After', '9')
                self.end_headers()
                self.wfile.write(reply)

        server = ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            proxy_port = sock.getsockname()[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cfg = root / 'config.json'
            cfg.write_text(json.dumps({'agent_id': 'native-integration', 'mode': 'observe',
                'max_trace_bytes': 4096, 'routes': [{'id': 'native',
                    'host_patterns': ['127.0.0.1'], 'ports': [server.server_port],
                    'methods': ['POST'], 'path_patterns': ['/messages/*'],
                    'protocol_plugin': 'anthropic-messages'}]}))
            with (root / 'proxy.log').open('w+') as log:
                process = subprocess.Popen(['mitmdump', '--quiet', '--mode', 'regular',
                    '--listen-host', '127.0.0.1', '--listen-port', str(proxy_port),
                    '--set', 'connection_strategy=lazy', '--set', 'confdir=' + str(root / 'ca'),
                    '-s', str(Path(addon.__file__).with_name('loader.py'))],
                    env={**os.environ, 'DEFUZEX_INTERCEPTOR_CONFIG': str(cfg)},
                    stdout=log, stderr=log)
                try:
                    deadline = time.monotonic() + 15
                    while True:
                        try:
                            with socket.create_connection(('127.0.0.1', proxy_port), timeout=.1):
                                break
                        except OSError:
                            if process.poll() is not None or time.monotonic() > deadline:
                                log.seek(0)
                                self.fail('Proxy did not start: ' + log.read())
                            time.sleep(.05)
                    payload = b'{ "model": "native", "tools": [{"defer_loading":true}] }'
                    for status in (401, 429, 200):
                        connection = http.client.HTTPConnection('127.0.0.1', proxy_port, timeout=10)
                        try:
                            connection.request('POST', f'http://127.0.0.1:{server.server_port}/messages/{status}',
                                body=payload, headers={'Authorization': 'Bearer native-secret',
                                                       'Content-Type': 'application/json'})
                            response = connection.getresponse()
                            self.assertEqual(response.status, status)
                            self.assertEqual(response.getheader('Retry-After'), '9')
                            self.assertEqual(response.read(), stream if status == 200 else b'{"error":"native-secret"}')
                        finally:
                            connection.close()
                    self.assertEqual(received, [(f'/messages/{s}', 'Bearer native-secret', payload)
                                                for s in (401, 429, 200)])
                finally:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                log.seek(0)
                output = log.read()
            self.assertNotIn('native-secret', output)
            events = [json.loads(line.removeprefix('DEFUZEX_TRACE '))
                      for line in output.splitlines() if line.startswith('DEFUZEX_TRACE ')]
            responses = [e for e in events if e['event'] == 'llm_response']
            self.assertEqual([e['status'] for e in responses], [401, 429, 200])
            self.assertEqual(responses[-1]['raw_body'], stream.decode())
