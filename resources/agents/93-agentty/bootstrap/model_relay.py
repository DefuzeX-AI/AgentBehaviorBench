"""Loopback HTTP relay from agentty to the selected HTTPS model endpoint.

agentty sends POST /v1/chat/completions to its `--provider` host (and
GET /v1/models at startup). The runtime admits exactly
POST <selected-base>/chat/completions, so agentty
talks plain HTTP to this relay on 127.0.0.1, and the relay makes
POST <selected-base>/chat/completions through the runtime's HTTPS_PROXY (with
Python's default TLS context, which honors SSL_CERT_FILE), streaming the
response back unchanged. Anything else gets a local 404.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import urllib.error
import urllib.request

RELAYED_PATH = "/v1/chat/completions"
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
            if self.command != "POST" or self.path != RELAYED_PATH:
                self.send_error(404, "model relay: only POST /v1/chat/completions is available")
                return
            headers = {name: self.headers[name] for name in FORWARD_REQUEST_HEADERS if self.headers.get(name)}
            request = urllib.request.Request(upstream + MODEL_PATH, data=body, headers=headers,
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
