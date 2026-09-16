"""Issue #50: the viewer build is documented, and both viewer paths explain a missing build alike."""
import html
import json
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from agentbench.cli import viewer

ROOT = Path(__file__).resolve().parents[1]
READMES = [ROOT / 'README.md', *sorted((ROOT / 'docs' / 'otherLanguages').glob('README.*.md'))]


def _result_log(tmp_path):
    path = tmp_path / 'result.json'
    path.write_text(json.dumps([
        {'event': 'run_started', 'source': 'abb', 'suite_id': 'suite_docs',
         'timestamp': '2026-01-01T00:00:00+00:00', 'selected_agent_ids': ['demo']},
        {'event': 'suite_completed', 'source': 'abb', 'suite_id': 'suite_docs',
         'timestamp': '2026-01-01T00:00:01+00:00',
         'summary': {'selected': 1, 'attempted': 1, 'passed': 1, 'failed': 0, 'skipped': 0,
                     'suite_passed': True}},
    ]))
    return path


@pytest.mark.parametrize('sources', [True, False], ids=['checkout', 'no-sources'])
def test_server_page_and_cli_explain_a_missing_build_identically(tmp_path, monkeypatch, sources):
    web = tmp_path / 'web'
    (web / 'dist').mkdir(parents=True)
    if sources:
        (web / 'package.json').write_text('{}')
    monkeypatch.setattr(viewer, 'WEB_ROOT', web / 'dist')
    with pytest.raises(viewer.ViewerUnavailable) as expected:
        viewer.require_viewer_assets()

    server = viewer.create_viewer_server(_result_log(tmp_path), port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pytest.raises(HTTPError) as response:
            urlopen(f'http://127.0.0.1:{server.server_port}/suite/suite_docs/', timeout=3)
        body = response.value.read().decode('utf-8')
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    assert response.value.code == 503
    assert html.escape(str(expected.value), quote=False) in body
    assert 'npm install' not in body


@pytest.mark.parametrize('readme', READMES, ids=lambda path: path.name)
def test_every_readme_documents_the_viewer_build(readme):
    text = readme.read_text(encoding='utf-8')
    assert '(cd web && npm ci && npm run build)' in text
    assert 'Node.js 20.19' in text
