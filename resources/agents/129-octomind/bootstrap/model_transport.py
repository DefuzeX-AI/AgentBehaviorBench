"""Byte-preserving loopback transport for the native static TLS client.

The published octolib reqwest 0.12 client uses compiled WebPKI roots rather than
ABB's per-run CA environment. Native requests stay native; this local hop sends
those bytes to the selected HTTPS target with the normal verified ABB CA bundle
and HTTP proxy. No model selection, prompt, tool, response or verdict is changed.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit

PATHS = {'/v1/chat/completions': '/chat/completions', '/v1/models': '/models'}
HOP_HEADERS = {'host', 'connection', 'transfer-encoding', 'content-length', 'proxy-connection'}


def verified_target(environ):
    base = environ.get('ABB_AGENT_MODEL_BASE_URL', '').strip().rstrip('/')
    url = urlsplit(base)
    if (url.scheme != 'https' or not url.hostname or url.username or url.password
            or url.query or url.fragment or any(c.isspace() for c in base)):
        raise ValueError('A credential-free HTTPS base URL is required')
    return base


def handler(base, context):
    class Transport(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.forward()

        def do_POST(self):
            self.forward()

        def forward(self):
            if self.path not in PATHS or (self.command == 'GET') != self.path.endswith('/models'):
                self.send_error(404)
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 <= length <= 32 * 1024 * 1024:
                    self.send_error(413)
                    return
                data = self.rfile.read(length) if length else None
                headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP_HEADERS}
                request = urllib.request.Request(base + PATHS[self.path], data=data,
                                                 headers=headers, method=self.command)
                try:
                    reply = urllib.request.urlopen(request, context=context, timeout=180)
                except urllib.error.HTTPError as error:
                    reply = error
                with reply:
                    self.send_response(reply.status)
                    for key, value in reply.headers.items():
                        if key.lower() not in HOP_HEADERS:
                            self.send_header(key, value)
                    self.send_header('Connection', 'close')
                    self.end_headers()
                    while block := reply.read1(65536):
                        self.wfile.write(block)
                        self.wfile.flush()
                self.close_connection = True
            except (BrokenPipeError, ConnectionResetError):
                self.close_connection = True
            except (OSError, ValueError) as error:
                # No native request content, credential or upstream error body is logged.
                print('Octomind verified model transport failed: ' + type(error).__name__,
                      file=sys.stderr, flush=True)
                self.send_error(502, 'Verified model transport failed')
    return Transport


def serve():
    base = verified_target(os.environ)
    context = ssl.create_default_context(cafile=os.environ.get('SSL_CERT_FILE') or None)
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler(base, context))
    print(server.server_address[1], flush=True)
    server.serve_forever()


def start_transport():
    # This child inherits the ACP process group and is killed by ABB teardown.
    child = subprocess.Popen([sys.executable, str(Path(__file__).resolve())],
                             stdout=subprocess.PIPE, stdin=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, text=True)
    import select
    if not select.select([child.stdout], [], [], 15)[0]:
        child.terminate()
        raise ValueError('Native model transport startup exceeded its deadline')
    port = child.stdout.readline().strip()
    if not port.isdigit() or not 1 <= int(port) <= 65535:
        child.terminate()
        raise ValueError('Native model transport did not return a loopback port')
    return 'http://127.0.0.1:' + port + '/v1'


if __name__ == '__main__':
    serve()
