"""Loopback HTTP relay from Zeph to the selected HTTPS model endpoint.

Zeph opens connections to the model host that are not the admitted model route
before its first chat call; in the first smoke the runtime then sent the chat
call itself through the egress observer, which refused it. Zeph talks plain
HTTP to this relay on 127.0.0.1 instead; the relay makes each
POST /chat/completions on a fresh HTTPS connection with Python's default
context (which honors SSL_CERT_FILE) through the runtime's HTTPS_PROXY and
streams the response back unchanged. Anything else gets a local 404.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import urllib.error
import urllib.request

MODEL_PATH = "/chat/completions"
FORWARD_REQUEST_HEADERS = ("Authorization", "Content-Type", "Accept", "User-Agent")
DROP_RESPONSE_HEADERS = {"connection", "content-length", "transfer-encoding", "keep-alive"}


def start(upstream: str) -> tuple[ThreadingHTTPServer, str]:
    """Serve on an ephemeral loopback port; return the server and its base URL."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler())

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _relay(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else None
            if self.command != "POST" or self.path != MODEL_PATH:
                self.send_error(404, "model relay: only POST /chat/completions is available")
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
