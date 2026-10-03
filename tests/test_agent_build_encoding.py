"""Onboarding text must not depend on a Windows GBK process locale."""
import copy
import json
from pathlib import Path

from agentbench.onboarding.build_agent_env.frameworks.langgraph.manifest import stage_validation
from tests.agent_build_fixtures import source, plan, Client, build, FILES


def gbk_default(monkeypatch):
    original = Path.open

    def open_path(path, mode='r', buffering=-1, encoding=None, errors=None, newline=None):
        if 'b' not in mode and encoding in (None, 'locale'):
            encoding = 'gbk'
        return original(path, mode, buffering, encoding, errors, newline)

    monkeypatch.setattr(Path, 'open', open_path)


def test_staging_source_preserves_utf8_bytes_under_gbk(tmp_path, monkeypatch):
    source_path = tmp_path / 'graph.py'
    original = '# Beacon — 中文 😀\r\ngraph = None\r\n'.encode('utf-8')
    source_path.write_bytes(original)
    gbk_default(monkeypatch)
    stage_validation(tmp_path / 'staged', 'graph.py', source_path)
    assert (tmp_path / 'staged/agent/graph.py').read_bytes() == original


def test_build_and_resume_unicode_files_under_gbk(source, plan, monkeypatch):
    graph = source.directory / 'agent/langgraph.json'
    descriptor = {'graphs': {'agent': './src/pkg/graph.py:graph'},
                  'description': 'Beacon — 中文 😀'}
    original = json.dumps(descriptor, ensure_ascii=False).encode('utf-8')
    graph.write_bytes(original)
    files = {**FILES,
             'bindings/bridge.py': '# 中文 — 😀\n' + FILES['bindings/bridge.py'],
             'Dockerfile': '# 中文 — 😀\n' + FILES['Dockerfile'],
             'requirement.md': FILES['requirement.md'].replace('Return the input text.', 'Return 中文 — 😀 unchanged.')}

    class UnicodeClient(Client):
        def generate(self, payload, **kwargs):
            response = copy.deepcopy(super().generate(payload, **kwargs))
            if payload.get('response_kind') == 'configuration_facts':
                response['facts']['display_name'] = 'Beacon — 中文 😀'
            return response

    gbk_default(monkeypatch)
    client = UnicodeClient(plan, files=files)
    assert build(source, plan, client=client).status == 'generated'
    assert graph.read_bytes() == original
    manifest = (source.directory / 'agent.toml').read_text(encoding='utf-8')
    assert 'Beacon — 中文 😀' in manifest
    for name in ('bindings/bridge.py', 'Dockerfile', 'requirement.md'):
        assert (source.directory / name).read_text(encoding='utf-8') == files[name]
    resumed = UnicodeClient(plan, files=files)
    assert build(source, plan, client=resumed).status == 'generated'
    assert resumed.requests == []
