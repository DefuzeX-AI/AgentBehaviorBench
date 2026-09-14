"""Issue #37: redirected stdout receives the viewer URL before serving."""
import json
from types import SimpleNamespace

from agentbench.cli import viewer


def test_startup_flushes_before_serve_forever(monkeypatch, tmp_path):
    path = tmp_path/'run.json'
    path.write_text(json.dumps({'suite_id': 'suite'}))
    buffered, visible = [], []

    def write(text):
        buffered.append(text)

    def flush():
        visible.extend(buffered)
        buffered.clear()

    def serve():
        assert 'http://127.0.0.1:9999' in ''.join(visible)

    monkeypatch.setattr('sys.stdout', SimpleNamespace(write=write, flush=flush))
    monkeypatch.setattr(viewer, 'require_viewer_assets', lambda: None)
    monkeypatch.setattr(viewer, 'create_viewer_server', lambda *a, **kw: SimpleNamespace(
        server_port=9999, serve_forever=serve, server_close=lambda: None))
    viewer.serve_result_log(path)
