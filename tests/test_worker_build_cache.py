"""Host CLI/onboarding edits must not invalidate container images."""
from pathlib import Path
from types import SimpleNamespace

from agentbench.runtime.docker import worker_build
from agentbench.runtime.docker.image_builder import _content_digest


def test_host_tools_do_not_invalidate_worker_but_runtime_changes_do(tmp_path, monkeypatch):
    package = tmp_path / 'agentbench'
    for name, content in {
        '__init__.py': '',
        '__main__.py': 'from agentbench.cli.main import cli',
        'cli/main.py': '# host CLI',
        'onboarding/example.md': 'host prompt',
        'runtime/docker/worker_build.py': '# staging helper',
        'runtime/docker/requirements.txt': '',
        'runtime/agentcontainer/worker.py': '# actual runtime',
    }.items():
        path = package / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    monkeypatch.setattr(worker_build, '__file__', str(package / 'runtime/docker/worker_build.py'))
    monkeypatch.setattr(worker_build, 'stage_adapter_dependencies', lambda *args: None)
    root = tmp_path / 'unit'
    root.mkdir()
    (root / 'Dockerfile').write_text('FROM scratch\nUSER agent\n')
    config = SimpleNamespace(agent_root=root, build_context=root, dockerfile=root / 'Dockerfile')

    def fingerprint():
        with worker_build.worker_build_context(config) as (context, _):
            return _content_digest(context)

    baseline = fingerprint()
    assert fingerprint() == baseline  # Different TemporaryDirectory, same inputs.
    (package / 'cli/main.py').write_text('# changed CLI')
    (package / 'onboarding/example.md').write_text('changed prompt')
    assert fingerprint() == baseline
    (package / 'runtime/agentcontainer/worker.py').write_text('# changed runtime')
    assert fingerprint() != baseline
