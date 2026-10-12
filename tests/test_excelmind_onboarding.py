"""Offline integration checks; these do not replace real Docker smoke."""
import ast
import csv
import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
UNIT = ROOT / 'resources/agents/49-excelmind'


def test_pinned_upstream_source_unchanged():
    if not (UNIT / 'agent').is_dir():
        pytest.skip('Requires restored ExcelMind upstream source')
    manifest = json.loads((UNIT / 'source-manifest.json').read_text())
    assert manifest['revision'] == 'd8bc5c8bdd26e5bf5944807a01cc4732bb0250a9'
    for entry in manifest['files']:
        data = (UNIT / 'agent' / entry['path']).read_bytes()
        assert hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() == entry['git_blob_sha1']


def test_public_synthetic_fixture():
    with (UNIT / 'fixtures/sales.csv').open() as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 6
    assert sum(int(row['revenue']) for row in rows) == 1500
    assert sum(int(row['revenue']) for row in rows if row['region'] == 'East') == 780


def test_binding_factory_and_native_graph():
    source = (UNIT / 'bindings/bridge.py').read_text()
    tree = ast.parse(source)
    factory = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'create_graph')
    assert not factory.args.args
    assert 'from excel_agent.graph import get_graph, reset_graph' in source
    assert 'self.graph.invoke' in source
    assert 'except' not in source
