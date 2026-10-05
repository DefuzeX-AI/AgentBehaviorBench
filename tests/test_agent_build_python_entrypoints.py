"""Discover installed Python CLIs and their source evidence without executing them."""
from dataclasses import replace
from pathlib import Path

import pytest

from agentbench.onboarding.discovery import discover_files
from agentbench.onboarding.source import DownloadedAgent
from agentbench.onboarding.build_agent_env.openrouter_provider.context import collect_context
from agentbench.onboarding.build_agent_env.openrouter_provider.settings import load_settings


def write(root, name, text):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


@pytest.mark.parametrize('prefix', ['# command help\n' * 100, '"""' + '中文' * 200 + '"""\n'])
def test_pyproject_cli_dependencies_are_collected_even_when_cli_is_truncated(tmp_path, prefix):
    root = tmp_path / 'agent'
    write(root, 'pyproject.toml', '[project]\nname="native-agent"\n[project.scripts]\nagent="pkg.cli:app"\n')
    write(root, 'src/pkg/cli.py', prefix + 'from pkg.graph import build_graph\nfrom pkg.state import State\n'
          'raise AssertionError("never execute upstream")\n')
    write(root, 'src/pkg/graph.py', 'from pkg.nodes.analyst import run\ndef build_graph(): return run\n')
    write(root, 'src/pkg/state.py', 'class State: pass\n')
    write(root, 'src/pkg/nodes/analyst.py', 'def run(): pass\n')
    files = discover_files(root)
    assert 'src/pkg/cli.py' in files
    source = DownloadedAgent(tmp_path, 'https://github.com/example/native-agent', 'revision', files)
    settings = replace(load_settings(), max_file_bytes=200, max_files=5)
    context = collect_context(source, settings, {})
    names = {item['path'] for item in context['files']}
    assert {'pyproject.toml', 'src/pkg/cli.py', 'src/pkg/graph.py', 'src/pkg/state.py'} <= names
    assert next(item for item in context['files'] if item['path'].endswith('/cli.py'))['truncated']
    assert context['content_bytes'] <= settings.max_context_bytes


def test_pyproject_entrypoint_cannot_escape_the_source_root(tmp_path):
    root = tmp_path / 'agent'
    write(tmp_path, 'private.py', 'PRIVATE = "host data"\n')
    write(root, 'pyproject.toml', '[project]\nname="native-agent"\n[project.scripts]\n'
          'bad="../private:run"\n[tool.setuptools.package-dir]\n""=".."\n')
    assert discover_files(root) == ('pyproject.toml',)
