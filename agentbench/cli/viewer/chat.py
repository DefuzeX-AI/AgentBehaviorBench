"""Serve the chat page and its JSON API for ``agentbench chat --view``.

The page is the built viewer (web/dist) with two injected meta tags: the chat
API base and a per-process control token. Reads follow the viewer's
same-origin rule; every command (send, end, mark) additionally needs the
Origin header and the token, as Suite control commands do.
"""
from __future__ import annotations

import json
import re
import secrets
import threading
from html import escape
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler
from urllib.parse import urlparse

from .control import local_origin, read_command
from .server import DEFAULT_HOST, DEFAULT_PORT, WEB_ROOT, ViewerHTTPServer, _static_path, require_viewer_assets

API = "/api/chat"
PAGE = "/chat/"


def build_chat_handler(controller, token):
    class ChatHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            super().__init__(*args, directory=str(WEB_ROOT), **kwargs)

        def log_message(self, format, *args):
            return

        def do_GET(self):
            path = urlparse(self.path).path
            if path.startswith("/api/"):
                if not local_origin(self.headers):
                    return self._json({"error": "Same-origin reads only"}, HTTPStatus.FORBIDDEN)
                try:
                    if path == API + "/state":
                        return self._json(controller.state())
                    if path == API + "/trajectory":
                        return self._json(controller.trajectory())
                    raw = re.fullmatch(re.escape(API) + r"/turns/(\d{1,4})/raw", path)
                    if raw:
                        return self._json(controller.raw(int(raw[1])))
                except (KeyError, OSError, ValueError):
                    return self._json({"error": "Record unavailable"}, HTTPStatus.NOT_FOUND)
                return self._json({"error": "Unknown chat API"}, HTTPStatus.NOT_FOUND)
            if path in ("/", PAGE.rstrip("/"), PAGE):
                return self._page()
            self.path = _static_path(path)
            return super().do_GET()

        def do_POST(self):
            path = urlparse(self.path).path
            if not local_origin(self.headers, require_origin=True):
                return self._json({"error": "Same-origin commands only"}, HTTPStatus.FORBIDDEN)
            if not secrets.compare_digest(self.headers.get("X-ABB-Control-Token", ""), token):
                return self._json({"error": "Invalid control credential"}, HTTPStatus.FORBIDDEN)
            try:
                payload = read_command(self.headers, self.rfile)
                if path == API + "/turns":
                    if "input" not in payload:
                        raise ValueError("A turn needs an input")
                    return self._json(controller.submit(payload["input"]), HTTPStatus.ACCEPTED)
                if path == API + "/end":
                    controller.end()
                    return self._json(controller.state(), HTTPStatus.ACCEPTED)
                if path == API + "/marks":
                    return self._json(controller.mark(payload.get("trajectory_id"), payload.get("step_id"),
                                                      payload.get("reason")), HTTPStatus.CREATED)
                if path == API + "/marks/delete":
                    controller.unmark(payload.get("trajectory_id"), payload.get("step_id"), payload.get("created_at"))
                    return self._json({"ok": True})
            except KeyError:
                return self._json({"error": "Unknown step or mark"}, HTTPStatus.NOT_FOUND)
            except ValueError as exc:
                return self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except RuntimeError as exc:
                return self._json({"error": str(exc)}, HTTPStatus.CONFLICT)
            return self._json({"error": "Unknown chat command"}, HTTPStatus.NOT_FOUND)

        def _page(self):
            index = WEB_ROOT / "index.html"
            html = index.read_text(encoding="utf-8")
            meta = (f'<meta name="abb-chat-api" content="{escape(API, quote=True)}">'
                    f'<meta name="abb-chat-token" content="{escape(token, quote=True)}">')
            body = html.replace("<head>", "<head>" + meta, 1).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, payload, status=HTTPStatus.OK):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            try:
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                self.close_connection = True

    return ChatHandler


def start_chat_viewer(controller, *, host=DEFAULT_HOST, port=DEFAULT_PORT):
    """Serve the chat page in a daemon thread; return (server, url)."""
    require_viewer_assets()
    handler = build_chat_handler(controller, secrets.token_urlsafe(32))
    try:
        server = ViewerHTTPServer((host, port), handler)
    except OSError:
        if port == 0:
            raise
        server = ViewerHTTPServer((host, 0), handler)
    threading.Thread(target=server.serve_forever, name="abb-chat-viewer", daemon=True).start()
    return server, f"http://{host}:{server.server_port}{PAGE}"
