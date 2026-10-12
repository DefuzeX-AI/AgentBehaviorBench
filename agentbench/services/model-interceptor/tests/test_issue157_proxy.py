"""Real HTTP/1.1 disconnects after complete and incomplete SSE replies."""
import gzip
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


class EarlyDisconnectProxyTest(unittest.TestCase):
    def test_disconnect_after_done_retains_reply_but_partial_stream_is_an_error(self):
        partial = b'data: {"choices":[{"delta":{"content":"hello"}}]}\n\n'
        full = partial + b'data: {"choices":[],"usage":{"total_tokens":9}}\n\ndata: [DONE]\n\n'
        bodies = {'complete': full, 'compressed': gzip.compress(full), 'partial': partial}
        release = threading.Event()

        class Upstream(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'
            def log_message(self, *args):
                pass
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                case = self.path.rsplit('/', 1)[-1]
                body = bodies[case]
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Transfer-Encoding', 'chunked')
                if case == 'compressed':
                    self.send_header('Content-Encoding', 'gzip')
                self.end_headers()
                self.wfile.write(f'{len(body):x}\r\n'.encode() + body + b'\r\n')
                self.wfile.flush()
                # The client closes before the HTTP chunked-body terminator.
                release.wait(20)
                try:
                    self.wfile.write(b'0\r\n\r\n')
                    self.wfile.flush()
                except OSError:
                    pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.addCleanup(release.set)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cfg = root / 'config.json'
            cfg.write_text(json.dumps({'agent_id': 'issue157', 'mode': 'observe', 'max_trace_bytes': 1024,
                'routes': [{'id': 'native', 'host_patterns': ['127.0.0.1'], 'ports': [server.server_port],
                'methods': ['POST'], 'path_patterns': ['/stream/*'], 'protocol_plugin': 'openai-chat'}]}))
            log_path = root / 'proxy.log'
            def events():
                found = []
                for line in log_path.read_text().splitlines():
                    if line.startswith('DEFUZEX_TRACE '):
                        try:
                            found.append(json.loads(line.removeprefix('DEFUZEX_TRACE ')))
                        except json.JSONDecodeError:
                            pass  # The writer may still be publishing the final line.
                return found

            with log_path.open('w+') as log:
                process = subprocess.Popen(['mitmdump', '--quiet', '--mode', 'regular',
                    '--listen-host', '127.0.0.1', '--listen-port', str(port),
                    '--set', 'connection_strategy=lazy', '--set', 'confdir=' + str(root / 'ca'),
                    '-s', str(Path(addon.__file__).with_name('loader.py'))],
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
                    for case, wire in bodies.items():
                        with self.subTest(case=case):
                            connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
                            reply = None
                            try:
                                connection.request('POST', f'http://127.0.0.1:{server.server_port}/stream/{case}',
                                    body=b'{"model":"fixture","stream":true,"messages":[]}',
                                    headers={'Content-Type': 'application/json', 'Authorization': 'Bearer native-secret'})
                                reply = connection.getresponse()
                                self.assertEqual(reply.read(len(wire)), wire)
                                if case == 'compressed':
                                    self.assertEqual(reply.getheader('Content-Encoding'), 'gzip')
                                connection.sock.shutdown(socket.SHUT_RDWR)
                            finally:
                                if reply is not None:
                                    reply.close()
                                connection.close()
                            deadline = time.monotonic() + 5
                            while True:
                                terminal = [e for e in events() if e.get('path') == f'/stream/{case}'
                                            and e['event'] in ('llm_response', 'llm_error', 'observation_error')]
                                if terminal or time.monotonic() > deadline:
                                    break
                                time.sleep(.02)
                            self.assertEqual(len(terminal), 1, log_path.read_text())
                            result = terminal[0]
                            if case == 'partial':
                                self.assertEqual(result['event'], 'llm_error')
                                self.assertEqual(result['error_code'], 'transport_error')
                            else:
                                self.assertEqual(result['event'], 'llm_response', result)
                                self.assertTrue(result['client_closed_early'])
                                self.assertEqual(result['raw_body'], full.decode())
                                self.assertEqual(result['payload']['events'][-1]['usage']['total_tokens'], 9)
                finally:
                    release.set()
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    if os.environ.get('ABB_INTERCEPTOR_TEST_ARTIFACTS'):
                        output = Path(os.environ['ABB_INTERCEPTOR_TEST_ARTIFACTS'])
                        output.mkdir(parents=True, exist_ok=True)
                        (output / 'issue157-proxy.log').write_text(log_path.read_text())
                        (output / 'issue157-events.json').write_text(json.dumps(events(), indent=2))
            self.assertNotIn('native-secret', log_path.read_text())
