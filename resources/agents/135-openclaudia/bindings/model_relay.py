"""Loopback HTTP relay from OpenClaudia (rustls) to the ABB model interceptor.

OpenClaudia's reqwest client uses ``rustls-tls`` with bundled webpki roots and
ignores ``SSL_CERT_FILE``, so it cannot verify the runtime interceptor CA.
OpenClaudia talks plain HTTP to this relay on 127.0.0.1 (``--target local``);
the relay makes the HTTPS request with Python's default context (which honors
``SSL_CERT_FILE``) through the runtime's ``HTTPS_PROXY``, and streams the
response back unchanged. Same approach as 113-sudocode / 81-aster.

OpenClaudia's openai-compatible adapter posts to ``<base>/v1/chat/completions``.
"""

from __future__ import annotations

import os
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROUTES = {("POST", "/v1/chat/completions"), ("GET", "/v1/models"), ("GET", "/models")}
FORWARD_REQUEST_HEADERS = (
    "Authorization",
    "Content-Type",
    "Accept",
    "User-Agent",
    "X-Request-Id",
)
DROP_RESPONSE_HEADERS = {
    "connection",
    "content-length",
    "transfer-encoding",
    "keep-alive",
}


def start(upstream: str, *, bearer: str | None = None) -> tuple[ThreadingHTTPServer, str]:
    """Serve on an ephemeral loopback port; return the server and its base URL."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler())
    upstream = upstream.rstrip("/")

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _relay(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else None
            if (self.command, self.path.split("?", 1)[0]) not in ROUTES:
                self.send_error(
                    404,
                    "model relay: only OpenAI chat/completions and models routes",
                )
                return
            headers = {
                name: self.headers[name]
                for name in FORWARD_REQUEST_HEADERS
                if self.headers.get(name)
            }
            if bearer and "Authorization" not in headers:
                headers["Authorization"] = f"Bearer {bearer}"
            request = urllib.request.Request(
                upstream + self.path,
                data=body,
                headers=headers,
                method=self.command,
            )
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
                self.send_header("Connection", "close")
                self.end_headers()
                while chunk := response.read1(65536):
                    self.wfile.write(chunk)
                    self.wfile.flush()
            self.close_connection = True

        do_GET = do_POST = _relay

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def default_upstream() -> str:
    """Admitted OpenAI chat host; interceptor rewrites via HTTPS_PROXY."""
    return os.environ.get("ABB_MODEL_RELAY_UPSTREAM", "https://api.openai.com").rstrip("/")
