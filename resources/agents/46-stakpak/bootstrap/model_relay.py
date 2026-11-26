"""Loopback HTTP relay from Stakpak to the selected HTTPS model endpoint.

Over ACP Stakpak only resolves models prefixed anthropic/, openai/ or google/, so the
unit uses its built-in OpenAI provider with model "openai/<model>". With a non-OpenAI
api_endpoint that provider sends POST <api_endpoint>/chat/completions, keeps the
"openai/" prefix in the request's model field, and reads its key from OPENAI_API_KEY.
The api_endpoint is this relay on 127.0.0.1 (http://127.0.0.1:<port>/v1) and
OPENAI_API_KEY is a placeholder, so the real key never reaches Stakpak's config or
environment. The relay makes POST <selected-base>/chat/completions through the
runtime's HTTPS_PROXY (with Python's default TLS context, which honors SSL_CERT_FILE),
strips the "openai/" prefix from the model field, sets the Authorization header to the
selected key, and streams the response back unchanged. Anything else gets a local 404.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import urllib.error
import urllib.request

RELAYED_PATH = "/v1/chat/completions"
MODEL_PATH = "/chat/completions"
FORWARD_REQUEST_HEADERS = ("Content-Type", "Accept", "User-Agent")
DROP_RESPONSE_HEADERS = {"connection", "content-length", "transfer-encoding", "keep-alive"}
MODEL_PREFIX = "openai/"


def strip_model_prefix(body: bytes | None) -> bytes | None:
    """Return the request body with "openai/" removed from its model field."""
    if not body:
        return body
    try:
        payload = json.loads(body)
    except ValueError:
        return body
    model = payload.get("model") if isinstance(payload, dict) else None
    if not isinstance(model, str) or not model.startswith(MODEL_PREFIX):
        return body
    payload["model"] = model[len(MODEL_PREFIX):]
    return json.dumps(payload, separators=(",", ":")).encode()


def start(upstream: str, key: str) -> tuple[ThreadingHTTPServer, str]:
    """Serve on an ephemeral loopback port; return the server and its origin URL."""
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
            headers["Authorization"] = f"Bearer {key}"
            request = urllib.request.Request(upstream + MODEL_PATH, data=strip_model_prefix(body), headers=headers,
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
