"""Pre-SDK source restoration using real local Git commits and no network."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
import subprocess
import zipfile

import pytest

from agentbench.runtime.source import prepare_agent_source, source_spec
from agentbench.runtime.source import git as acquisition
from agentbench.runtime.agentcontainer.config import tomllib


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


@pytest.fixture
def unit(tmp_path, monkeypatch):
    upstream = tmp_path / 'upstream'; upstream.mkdir()
    git(upstream, 'init', '-q')
    git(upstream, 'config', 'user.email', 'test@example.com')
    git(upstream, 'config', 'user.name', 'Test')
    (upstream / 'app.py').write_text('version = 1\n')
    git(upstream, 'add', '.')
    git(upstream, 'commit', '-qm', 'first')
    revision = git(upstream, 'rev-parse', 'HEAD')
    (upstream / 'app.py').write_text('version = 2\n')
    git(upstream, 'commit', '-qam', 'second')
    original = acquisition.run_git
    fetched = []
    def local_fetch(directory, args, check):
        if args[0] == 'fetch':
            fetched.append(args[-1])
            args = ['-c', 'protocol.file.allow=always', *args[:-2], str(upstream), args[-1]]
        return original(directory, args, check)
    monkeypatch.setattr(acquisition, 'run_git', local_fetch)
    root = tmp_path / 'project/resources/agents/01-test'; root.mkdir(parents=True)
    (root / 'agent.toml').write_text(f'''agent_id = "test"
framework = "langgraph"
[source]
method = "git"
repository = "https://example.com/agent.git"
revision = "{revision}"
[runtime]
type = "docker"
[build]
context = "."
dockerfile = "Dockerfile"
[launch]
argv = ["python", "worker.py"]
''')
    (root / 'Dockerfile').write_text('FROM python:3.12\nUSER agent\n')
    (root / 'requirement.md').write_text('Test profile')
    return root, revision, fetched


def prepare(root, tmp_path):
    prepare_agent_source(root, cache_dir=tmp_path/'cache')


def test_restore_pinned_version_then_repair_missing_file_without_refetch(unit, tmp_path):
    root, revision, fetched = unit
    manifest = (root/'agent.toml').read_bytes()
    dockerfile = (root/'Dockerfile').read_bytes()
    prepare(root, tmp_path)
    assert (root/'agent/app.py').read_text() == 'version = 1\n'
    prepare(root, tmp_path)
    (root/'agent/app.py').unlink()
    prepare(root, tmp_path)
    assert (root/'agent/app.py').read_text() == 'version = 1\n'
    assert fetched == [revision]
    assert (root/'agent.toml').read_bytes() == manifest
    assert (root/'Dockerfile').read_bytes() == dockerfile


def test_existing_local_source_not_overwritten_or_downloaded(unit, tmp_path):
    root, _, fetched = unit
    (root/'agent').mkdir()
    (root/'agent/app.py').write_text('local edits')
    prepare(root, tmp_path)
    assert (root/'agent/app.py').read_text() == 'local edits'
    assert not fetched


def test_modified_managed_source_blocks_instead_of_overwriting(unit, tmp_path):
    root, _, _ = unit
    prepare(root, tmp_path)
    (root/'agent/app.py').write_text('local edits')
    with pytest.raises(ValueError, match='modified'):
        prepare(root, tmp_path)
    assert (root/'agent/app.py').read_text() == 'local edits'


def test_failed_download_leaves_no_source_or_reusable_archive(unit, tmp_path, monkeypatch):
    root, _, _ = unit
    def fail(*args):
        raise RuntimeError('offline')
    monkeypatch.setattr(acquisition, 'run_git', fail)
    with pytest.raises(RuntimeError, match='offline'):
        prepare(root, tmp_path)
    assert not (root/'agent').exists()
    assert not list((tmp_path/'cache').glob('*.zip'))


def test_concurrent_restoration_downloads_once(unit, tmp_path):
    root, _, fetched = unit
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(prepare, root, tmp_path) for _ in range(2)]
        for job in jobs:
            job.result()
    assert len(fetched) == 1


def test_missing_integration_config_fails_before_download(unit, tmp_path):
    root, _, fetched = unit
    (root/'Dockerfile').unlink()
    with pytest.raises(FileNotFoundError, match='Dockerfile'):
        prepare(root, tmp_path)
    assert not fetched


def test_bundled_packages_remain_unchanged(unit, tmp_path):
    root, _, fetched = unit
    path = root/'agent.toml'
    path.write_text(path.read_text().replace('method = "git"', 'method = "bundled"'))
    with pytest.raises(FileNotFoundError, match='Bundled'):
        prepare(root, tmp_path)
    (root/'agent').mkdir()
    (root/'agent/package.json').write_text('{}')
    prepare(root, tmp_path)
    assert (root/'agent/package.json').read_text() == '{}'
    assert not fetched


def test_registry_accepts_missing_git_source_without_fetching(unit):
    from agentbench.harness.registry import _parse_agent
    root, _, fetched = unit
    agent = _parse_agent(dict(agent_id='test',path='resources/agents/01-test',framework='langgraph'), root.parents[2])
    assert agent.path == root
    assert not fetched


def test_all_sources_prepared_before_sdk_factory_opens(unit, tmp_path, monkeypatch):
    from agentbench.harness import SuiteRunner
    from agentbench.harness.registry import _parse_agent
    from agentbench.runtime import source
    root, _, fetched = unit
    original = source.prepare_agent_source
    monkeypatch.setattr(source, 'prepare_agent_source', lambda root, **kw: original(root, cache_dir=tmp_path/'cache', **kw))
    agent = _parse_agent(dict(agent_id='test',path='resources/agents/01-test',framework='langgraph'), root.parents[2])
    class SDKOpened(Exception):
        pass
    class Factory:
        supports_concurrency = False
        def open_suite(self, *args):
            assert (root/'agent/app.py').read_text() == 'version = 1\n'
            raise SDKOpened()
    with pytest.raises(SDKOpened):
        SuiteRunner(runner_factory=Factory()).run((agent,))
    assert len(fetched) == 1


def test_source_failure_prevents_sdk_open(unit, tmp_path, monkeypatch):
    from agentbench.harness import SuiteRunner, AgentRegistration
    from agentbench.runtime import source
    root, _, _ = unit
    calls = []
    def fail(*a, **kw):
        raise RuntimeError('source unavailable')
    monkeypatch.setattr(source, 'prepare_agent_source', fail)
    factory = SimpleNamespace(supports_concurrency=False, open_suite=lambda *a: calls.append('opened'))
    agent = AgentRegistration('test',root,True,'ready','langgraph','test')
    with pytest.raises(RuntimeError, match='source unavailable'):
        SuiteRunner(runner_factory=factory).run((agent,))
    assert calls == []


@pytest.mark.parametrize('name,content', [('../escape','bad'), ('model','version https://git-lfs.github.com/spec/v1\noid sha256:abc\n')])
def test_invalid_archive_does_not_publish_source(unit, tmp_path, monkeypatch, name, content):
    from agentbench.runtime.source import preparation
    root, _, _ = unit
    archive = tmp_path/'bad.zip'
    with zipfile.ZipFile(archive,'w') as file:
        file.writestr(name, content)
    monkeypatch.setattr(preparation,'source_archive',lambda *args: archive)
    with pytest.raises(ValueError):
        prepare(root,tmp_path)
    assert not (root/'agent').exists()


def test_sdk_staging_only_copies_prepared_files(unit, tmp_path, monkeypatch):
    from agentbench.sdk.plugin.kuma.image import evaluation_agent
    from agentbench.runtime.source import preparation
    root, _, fetched = unit
    prepare(root, tmp_path)
    def forbidden(*args):
        pytest.fail('SDK staging must not download Agent source')
    monkeypatch.setattr(preparation, 'source_archive', forbidden)
    with evaluation_agent(SimpleNamespace(path=root, agent_id='test', framework='langgraph'), backend=None) as staged:
        assert (staged.path/'agent/app.py').read_text() == 'version = 1\n'
    assert len(fetched) == 1


def test_install_mode_copies_repairs_and_never_clones(unit, tmp_path):
    root, _, fetched = unit
    path = root/'agent.toml'
    path.write_text(path.read_text().replace('method = "git"', 'method = "install"'))
    (root/'install').mkdir()
    (root/'install/package.json').write_text('{"name":"fixture"}')
    prepare(root,tmp_path)
    assert (root/'agent/package.json').read_bytes() == (root/'install/package.json').read_bytes()
    (root/'agent/package.json').unlink()
    prepare(root,tmp_path)
    assert (root/'agent/package.json').is_file()
    (root/'agent/package.json').write_text('local edit')
    with pytest.raises(ValueError,match='modified'):
        prepare(root,tmp_path)
    assert (root/'agent/package.json').read_text() == 'local edit'
    assert not fetched


def test_install_mode_requires_tracked_inputs(unit, tmp_path):
    root, _, fetched = unit
    path=root/'agent.toml'
    path.write_text(path.read_text().replace('method = "git"', 'method = "install"'))
    with pytest.raises(FileNotFoundError,match='installation directory'):
        prepare(root,tmp_path)
    assert not fetched


@pytest.mark.parametrize('number',range(18,30))
def test_migrated_acp_unit_can_prepare_from_install_only(number,tmp_path):
    import shutil
    from agentbench.harness.registry import _parse_agent
    base=Path(__file__).resolve().parents[1]
    unit=next((base/'resources/agents').glob(str(number)+'-*'))
    root=tmp_path/'resources/agents'/unit.name
    shutil.copytree(unit,root,ignore=lambda directory,names: {'agent'} if Path(directory)==unit else set())
    manifest=tomllib.loads((root/'agent.toml').read_text(encoding='utf-8'))
    record=dict(agent_id=manifest['agent_id'],framework='acp',path='resources/agents/'+unit.name)
    _parse_agent(record,tmp_path)
    assert not (root/'agent').exists()
    prepare(root,tmp_path)
    for source in (root/'install').rglob('*'):
        if source.is_file():
            assert (root/'agent'/source.relative_to(root/'install')).read_bytes()==source.read_bytes()
    _parse_agent(record,tmp_path)


def test_source_progress_uses_colored_running_success_and_failure():
    from agentbench.cli.terminal_ui.progress import ProgressPrinter
    from agentbench.cli.terminal_ui.constants import ANSI_GREEN, ANSI_RED, ANSI_YELLOW
    from agentbench.harness.progress import BenchmarkProgress
    lines=[]
    printer=ProgressPrinter(lines.append,live_updates=False)
    for status in ('started','succeeded','failed'):
        printer(BenchmarkProgress('source_preparation',status,agent_id='test',detail='Source'))
    assert ANSI_YELLOW+'RUNNING' in lines[0]
    assert '.... '+ANSI_GREEN+'OK' in lines[1]
    assert ANSI_RED+'FAILED' in lines[2]
