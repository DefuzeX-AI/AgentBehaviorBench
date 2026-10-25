"""Loopback HTTP relay from scode to the selected HTTPS model endpoint.

scode's HTTP client is reqwest with `rustls-tls`, which trusts only its bundled
webpki roots and ignores SSL_CERT_FILE, so it cannot verify the runtime's model
interceptor (the first smoke failed with "invalid peer certificate: UnknownIssuer"
and no intercepted request). scode talks plain HTTP to this relay on 127.0.0.1;
the relay makes the HTTPS request with Python's default context (which honors
SSL_CERT_FILE) through the runtime's HTTPS_PROXY, and streams the response back
unchanged. This is the same approach as the 81-aster unit.

Only the two routes the runtime admits are relayed: POST /chat/completions and
GET /models (scode's model catalog refresh, declared as model.metadata_paths).
Anything else gets a local 404 instead of a refused, retried request.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import urllib.error
import urllib.request

ROUTES = {("POST", "/chat/completions"), ("GET", "/models")}
FORWARD_REQUEST_HEADERS = ("Authorization", "Content-Type", "Accept", "User-Agent", "X-Request-Id")
DROP_RESPONSE_HEADERS = {"connection", "content-length", "transfer-encoding", "keep-alive"}


def start(upstream: str) -> tuple[ThreadingHTTPServer, str]:
    """Serve on an ephemeral loopback port; return the server and its base URL."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler())

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _relay(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else None
            if (self.command, self.path) not in ROUTES:
                self.send_error(404, "model relay: only POST /chat/completions and GET /models are available")
                return
            headers = {name: self.headers[name] for name in FORWARD_REQUEST_HEADERS if self.headers.get(name)}
            request = urllib.request.Request(upstream + self.path, data=body, headers=headers,
                                             method=self.command)
            try:
                response = opener.open(request, timeout=600)
            except urllib.error.HTTPError as exc:
                response = exc
            except OSError as exc:
                self.send_error(502, f"model relay: {type(exc).__name__}")
                return
            with response:
                self.send_response(response.status)
                for name, value in response.headers.items():
                    if name.lower() not in DROP_RESPONSE_HEADERS:
                        self.send_header(name, value)
                # Close-delimited body: streamed (SSE) responses pass through as
                # they arrive, without buffering for a Content-Length.
                self.send_header("Connection", "close")
                self.end_headers()
                while chunk := response.read1(65536):
                    self.wfile.write(chunk)
                    self.wfile.flush()
            self.close_connection = True

        do_GET = do_POST = _relay

        def log_message(self, format: str, *args: object) -> None:
            pass  # keep per-request logs out of the agent's stderr

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"
