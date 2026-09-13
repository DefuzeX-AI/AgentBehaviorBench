"""Local result viewer server for AgentBench JSON snapshots."""

from __future__ import annotations

import json
from html import escape
import threading
from dataclasses import dataclass
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse, parse_qs

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
WEB_ROOT = Path(__file__).resolve().parents[2] / "web" / "dist"


class ViewerUnavailable(OSError):
    """Prebuilt UI assets are absent or incomplete."""


def require_viewer_assets():
    import re
    index = WEB_ROOT / 'index.html'
    missing = not index.is_file()
    if not missing:
        for target in re.findall(r'(?:src|href)=["\']([^"\']+)["\']', index.read_text()):
            if target.startswith(('http:', 'https:', 'data:', '#')):
                continue
            asset = (WEB_ROOT / target.split('?')[0].lstrip('/')).resolve()
            if not asset.is_relative_to(WEB_ROOT.resolve()) or not asset.is_file():
                missing = True
                break
    if missing:
        import shlex
        raise ViewerUnavailable(f'Trace UI not built or incomplete. Run: cd {shlex.quote(str(WEB_ROOT.parent))} && npm ci && npm run build')


@dataclass(frozen=True)
class RunningViewer:
    """Background local viewer server."""

    server: ThreadingHTTPServer
    thread: threading.Thread
    base_url: str
    url: str

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


def serve_result_log(
    result_log: str | Path,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> None:
    """Serve the static viewer and result-log API until interrupted."""

    path = Path(result_log).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Result log is not a file: {path}" if path.exists()
                                else f"Result log not found: {path}")

    require_viewer_assets()
    server = create_viewer_server(path, host=host, port=port)
    base_url = f"http://{host}:{server.server_port}"
    url = _locked_viewer_url(base_url, _result_log_suite_id(path))
    # serve_forever() never returns on its own, so a block-buffered stdout — any
    # pipe or file — would hold both lines until the viewer is stopped.
    print(f"View: {url}", flush=True)
    print(f"Result log: {path}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nViewer stopped.")
    finally:
        server.server_close()


def start_viewer_server(
    result_log: str | Path,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> RunningViewer:
    """Start the result viewer in a daemon thread."""

    path = Path(result_log).resolve()
    suite_id = _result_log_suite_id(path)
    require_viewer_assets()
    server = create_viewer_server(path, host=host, port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://{host}:{server.server_port}"
    return RunningViewer(
        server=server,
        thread=thread,
        base_url=base_url,
        url=_locked_viewer_url(base_url, suite_id),
    )


def create_viewer_server(
    result_log: Path,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> ThreadingHTTPServer:
    """Create a local viewer server, falling back to a free port if needed."""

    handler = build_viewer_handler(
        result_log, expected_suite_id=_result_log_suite_id(result_log)
    )
    try:
        return ThreadingHTTPServer((host, port), handler)
    except OSError:
        if port == 0:
            raise
        return ThreadingHTTPServer((host, 0), handler)


def build_viewer_handler(
    result_log: Path, *, expected_suite_id: str | None
) -> type[SimpleHTTPRequestHandler]:
    """Build a request handler bound to one JSON result artifact."""
    run_api = None
    if result_log.name == 'run.json':
        try:
            metadata = json.loads(result_log.read_text(encoding='utf-8'))
            if isinstance(metadata, dict) and metadata.get('schema') in ('abb.observe.run.v1', 'abb.evaluate.run.v1'):
                from agentbench.observe.view_api import RunCatalogAPI
                run_api = RunCatalogAPI(result_log.parent)
        except (OSError, ValueError):
            pass
    suite_view = run_api is None
    if suite_view:
        from agentbench.observe.view_api import SuiteRunCatalogAPI
        run_api = SuiteRunCatalogAPI(result_log)

    class ViewerHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            super().__init__(*args, directory=str(WEB_ROOT), **kwargs)

        def log_message(self, format: str, *args: object) -> None:
            return

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if run_api is not None and parsed.path.startswith('/api/observe/'):
                origin = self.headers.get('Origin')
                host = self.headers.get('Host', '')
                if (urlparse(f'http://{host}').hostname not in ('localhost', '127.0.0.1', '::1')
                    or (origin and origin != f'http://{host}') or self.headers.get('Sec-Fetch-Site') == 'cross-site'):
                    self._send_json({'error': 'Same-origin reads only'}, status=HTTPStatus.FORBIDDEN)
                    return
                try:
                    self._send_json(run_api.route(parsed.path, parse_qs(parsed.query)))
                except (OSError, ValueError, KeyError, StopIteration):
                    self._send_json({'error': 'Artifact unavailable'}, status=HTTPStatus.NOT_FOUND)
                return
            result_api_path = _suite_result_api_path(expected_suite_id)
            if parsed.path == result_api_path:
                self._send_json(parse_result_log(result_log))
                return
            if parsed.path == "/api/result" or parsed.path.startswith(
                "/api/suites/"
            ):
                self._send_suite_mismatch()
                return
            if parsed.path == "/api/health":
                self._send_json({"ok": True})
                return

            suite_path = _suite_view_path(expected_suite_id)
            if parsed.path.rstrip("/") == suite_path.rstrip("/"):
                index = WEB_ROOT / "index.html"
                if not index.is_file():
                    self.send_error(HTTPStatus.SERVICE_UNAVAILABLE,
                                    "Trace UI not built. Run npm install and npm run build in web/.")
                    return
                html = index.read_text(encoding="utf-8")
                if suite_view:
                    html = html.replace("<head>", f'<head><meta name="abb-result-api" content="{escape(result_api_path, quote=True)}">', 1)
                body = html.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return
            if parsed.path in {"", "/"} and expected_suite_id is not None:
                self._send_suite_mismatch()
                return

            self.path = _static_path(parsed.path)
            super().do_GET()

        def _send_suite_mismatch(self) -> None:
            self._send_json(
                {
                    "error": "Suite ID does not match this result viewer.",
                    "suite_id": expected_suite_id,
                },
                status=HTTPStatus.CONFLICT,
            )

        def _send_json(
            self, payload: object, *, status: HTTPStatus = HTTPStatus.OK
        ) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    return ViewerHandler


def parse_result_log(path: str | Path) -> dict[str, object]:
    """Read a JSON event array into the shape consumed by the viewer."""

    result_path = Path(path)
    events: list[dict[str, object]] = []
    parse_errors: list[dict[str, object]] = []

    try:
        document = json.loads(result_path.read_text(encoding="utf-8"))
        if not isinstance(document, list):
            raise ValueError("Expected an array of event objects")
        for index, event in enumerate(document):
            if isinstance(event, dict):
                events.append(event)
            else:
                parse_errors.append({"index": index, "message": "Expected JSON object"})
    except (json.JSONDecodeError, ValueError) as exc:
        parse_errors.append({"message": str(exc)})

    suite_id: str | None = None
    selected_agent_ids: list[str] = []
    agents: list[dict[str, object]] = []
    step_events_by_agent: dict[str, list[dict[str, object]]] = {}
    summary: dict[str, object] | None = None
    suite_error: dict[str, object] | None = None

    for event in events:
        event_type = event.get("event")
        if event_type == "run_started":
            event_suite_id = event.get("suite_id")
            if isinstance(event_suite_id, str):
                suite_id = event_suite_id
            selected = event.get("selected_agent_ids")
            if isinstance(selected, list):
                selected_agent_ids = [str(agent_id) for agent_id in selected]
        elif event_type == "agent_completed":
            item = event.get("item")
            if isinstance(item, dict):
                agents.append(item)
        elif event_type in {"step_started", "step_completed", "step_failed"}:
            agent_id = event.get("agent_id")
            if isinstance(agent_id, str):
                step_events_by_agent.setdefault(agent_id, []).append(event)
        elif event_type == "suite_completed":
            event_summary = event.get("summary")
            if isinstance(event_summary, dict):
                summary = event_summary
        elif event_type == "suite_failed":
            error = event.get("error")
            if isinstance(error, dict):
                suite_error = error

    state = "complete" if summary is not None else "running_or_interrupted"
    if suite_error is not None:
        state = "failed"

    agents = _merge_step_events(agents, step_events_by_agent)

    return {
        "path": str(result_path),
        "suite_id": suite_id,
        "state": state,
        "selected_agent_ids": selected_agent_ids,
        "agents": agents,
        "summary": summary,
        "suite_error": suite_error,
        "parse_errors": parse_errors,
        "event_count": len(events),
        "events": events,
    }


def _result_log_suite_id(path: Path) -> str | None:
    """Read the Suite ID from the first valid run-start event."""

    suite_id = parse_result_log(path)["suite_id"]
    return suite_id if isinstance(suite_id, str) else None


def _locked_viewer_url(base_url: str, suite_id: str | None) -> str:
    if suite_id is None:
        return base_url
    return f"{base_url}{_suite_view_path(suite_id)}"


def _suite_view_path(suite_id: str | None) -> str:
    if suite_id is None:
        return "/"
    return f"/suite/{quote(suite_id, safe='')}/"


def _suite_result_api_path(suite_id: str | None) -> str:
    if suite_id is None:
        return "/api/result"
    return f"/api/suites/{quote(suite_id, safe='')}/result"


def _merge_step_events(
    agents: list[dict[str, object]],
    step_events_by_agent: dict[str, list[dict[str, object]]],
) -> list[dict[str, object]]:
    merged: list[dict[str, object]] = []
    seen: set[str] = set()

    for item in agents:
        agent_id = item.get("agent_id")
        if isinstance(agent_id, str):
            item = dict(item)
            item["step_events"] = step_events_by_agent.get(agent_id, [])
            seen.add(agent_id)
        merged.append(item)

    for agent_id, step_events in step_events_by_agent.items():
        if agent_id in seen:
            continue
        merged.append(
            {
                "agent_id": agent_id,
                "benchmark": None,
                "error": {
                    "type": "Incomplete",
                    "message": "Agent did not produce a final suite result.",
                },
                "step_events": step_events,
            }
        )

    return merged


def _static_path(path: str) -> str:
    static_path = unquote(path)
    if static_path in {"", "/"}:
        return "/index.html"
    return static_path
