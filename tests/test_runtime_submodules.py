"""Runnable preparation restores commit-pinned submodules with local Git repositories."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from agentbench.evaluation.targets import prepare_target
from agentbench.runtime.source import git as acquisition
from agentbench.runtime.source import prepare_agent_source
from agentbench.runtime.source.config import git_source_spec
from agentbench.runtime.source.export import export_archive
from tests.test_prepared_target import registration
from tests.test_runtime_source import unit, git  # noqa: F401
from tests.test_source_export import repository, commit, module

run_git = acquisition.run_git


def serve(monkeypatch, sources):
    fetched = []
    def fetch_local(directory, args, check):
        if args[0] == 'fetch':
            fetched.append(args[-2])
            args = ['-c', 'protocol.file.allow=always', *args[:-2], str(sources.get(args[-2], Path(directory) / 'missing')), args[-1]]
        return run_git(directory, args, check)
    monkeypatch.setattr(acquisition, 'run_git', fetch_local)
    return fetched


def point(root, url, revision):
    manifest = root / 'agent.toml'
    text = manifest.read_text().replace('https://example.com/agent.git', url)
    manifest.write_text(text.replace(text.split('revision = "')[1].split('"')[0], revision))


@pytest.fixture
def nested(unit, tmp_path, monkeypatch):
    root, _, _ = unit
    leaf = repository(tmp_path / 'leaf')
    (leaf / 'value.txt').write_text('pinned version')
    pinned = commit(leaf)
    (leaf / 'value.txt').write_text('new branch version')
    commit(leaf)
    child = repository(tmp_path / 'child')
    (child / 'lib.py').write_text('child = 1\n')
    commit(child)
    child_sha = module(child, 'vendor/leaf', '../leaf.git', pinned)
    parent = repository(tmp_path / 'parent')
    (parent / 'app.py').write_text('parent = 1\n')
    commit(parent)
    revision = module(parent, 'deps/child', 'git@example.com:org/child.git', child_sha)
    fetched = serve(monkeypatch, {f'https://example.com/org/{name}.git': path
                                  for name, path in [('parent', parent), ('child', child), ('leaf', leaf)]})
    point(root, 'https://example.com/org/parent.git', revision)
    return root, revision, fetched, [('deps/child', child_sha), ('deps/child/vendor/leaf', pinned)]


def published(cache):
    return [p for p in cache.iterdir() if p.is_dir()] if cache.exists() else []


def base_fingerprint(cache):
    [lock] = cache.glob('*.lock')
    return lock.stem


def test_prepared_target_contains_nested_submodule_files(nested, tmp_path, monkeypatch):
    root, revision, fetched, pins = nested
    cache = tmp_path / 'cache/prepared'
    target = prepare_target(registration(root), revision, cache_dir=cache)
    agent = target.registration.path / 'agent'
    assert (agent / 'app.py').read_text() == 'parent = 1\n'
    assert (agent / 'deps/child/lib.py').read_text() == 'child = 1\n'
    assert (agent / 'deps/child/vendor/leaf/value.txt').read_text() == 'pinned version'
    provenance = json.loads((target.registration.path / 'provenance.json').read_text())
    assert [(r['path'], r['revision']) for r in provenance['submodules']] == pins
    # The revision already fixes every gitlink commit, so no derived identity is needed.
    assert provenance['fingerprint'] == target.fingerprint == base_fingerprint(cache)
    key = hashlib.sha256(('https://example.com/org/parent.git\n' + revision).encode()).hexdigest()
    assert (tmp_path / 'cache/sources/recursive-v1' / (key + '.zip')).is_file()
    assert not (tmp_path / 'cache/sources' / (key + '.zip')).exists()
    # A prepared target is reused offline, without its source cache.
    shutil.rmtree(tmp_path / 'cache/sources')
    def offline(*args):
        raise RuntimeError('offline')
    monkeypatch.setattr(acquisition, 'run_git', offline)
    assert prepare_target(registration(root), revision, cache_dir=cache) == target


def test_runtime_source_restores_nested_submodules(nested, tmp_path):
    root, _, _, _ = nested
    prepare_agent_source(root, cache_dir=tmp_path / 'cache')
    assert (root / 'agent/deps/child/vendor/leaf/value.txt').read_text() == 'pinned version'


def test_source_without_submodules_keeps_plain_archive(unit, tmp_path):
    root, revision, fetched = unit
    spec = git_source_spec('https://example.com/agent.git', revision)
    archive, modules = export_archive(spec, tmp_path / 'sources', lambda: None)
    expected = tmp_path / 'expected.zip'
    acquisition.export_source(spec, expected, lambda: None)
    key = hashlib.sha256(('https://example.com/agent.git\n' + revision).encode()).hexdigest()
    assert (archive, modules) == ((tmp_path / 'sources' / (key + '.zip')).resolve(), [])
    assert archive.read_bytes() == expected.read_bytes()
    assert not (tmp_path / 'sources/recursive-v1').exists()
    cache = tmp_path / 'prepared'
    target = prepare_target(registration(root), revision, cache_dir=cache)
    assert target.fingerprint == base_fingerprint(cache)
    provenance = json.loads((target.registration.path / 'provenance.json').read_text())
    assert 'submodules' not in provenance
    assert provenance['archive_sha256'] == hashlib.sha256(expected.read_bytes()).hexdigest()


def pinned_parent(tmp_path, url='../leaf.git', leaf_files=None, gitmodules=True):
    leaf = repository(tmp_path / 'leaf')
    for name, write in (leaf_files or {'value.txt': lambda path: path.write_text('data')}).items():
        write(leaf / name)
    pinned = commit(leaf)
    parent = repository(tmp_path / 'parent')
    (parent / 'app.py').write_text('parent = 1\n')
    commit(parent)
    revision = module(parent, 'vendor/leaf', url, pinned)
    if not gitmodules:
        git(parent, 'rm', '-q', '.gitmodules')
        git(parent, 'commit', '-qm', 'drop gitmodules')
        revision = git(parent, 'rev-parse', 'HEAD')
    return parent, leaf, pinned, revision


def prepare_parent(root, tmp_path, monkeypatch, parent, leaf, revision):
    fetched = serve(monkeypatch, {'https://example.com/org/parent.git': parent,
                                  'https://example.com/org/leaf.git': leaf})
    point(root, 'https://example.com/org/parent.git', revision)
    return fetched, lambda: prepare_target(registration(root), revision, cache_dir=tmp_path / 'prepared')


def piped(root, text, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], input=text, text=True).strip()


def crafted_commit(parent, gitlink, pinned):
    """Write a tree Git's porcelain refuses: a gitlink at an escaping path."""
    def mktree(lines):
        return piped(parent, '\n'.join(lines) + '\n', 'mktree')
    app = git(parent, 'hash-object', '-w', 'app.py')
    modules = piped(parent, f'[submodule "dependency"]\npath = {gitlink}\nurl = ../leaf.git\n',
                     'hash-object', '-w', '--stdin')
    entries = [f'100644 blob {app}\tapp.py', f'100644 blob {modules}\t.gitmodules']
    head, _, last = gitlink.rpartition('/')
    link = f'160000 commit {pinned}\t{last}'
    entries.append(f'040000 tree {mktree([link])}\t{head}' if head else link)
    return git(parent, 'commit-tree', mktree(entries), '-m', 'escape')


@pytest.mark.parametrize('gitlink', ['..', 'vendor/..'])
def test_escaping_gitlink_path_is_rejected_before_fetch(unit, tmp_path, monkeypatch, gitlink):
    root, _, _ = unit
    parent, leaf, pinned, _ = pinned_parent(tmp_path)
    revision = crafted_commit(parent, gitlink, pinned)
    fetched, prepare = prepare_parent(root, tmp_path, monkeypatch, parent, leaf, revision)
    with pytest.raises(ValueError, match='Invalid submodule path: ' + gitlink):
        prepare()
    assert 'https://example.com/org/leaf.git' not in fetched
    assert not published(tmp_path / 'prepared')


@pytest.mark.parametrize('path', ['../escape', '/escape', 'vendor/../../escape'])
def test_escaping_gitmodules_path_is_rejected(unit, tmp_path, monkeypatch, path):
    root, _, _ = unit
    parent, leaf, _, _ = pinned_parent(tmp_path)
    text = (parent / '.gitmodules').read_text().replace('path = vendor/leaf', 'path = ' + path)
    (parent / '.gitmodules').write_text(text)
    git(parent, 'add', '.gitmodules')
    git(parent, 'commit', '-qm', 'escape')
    _, prepare = prepare_parent(root, tmp_path, monkeypatch, parent, leaf, git(parent, 'rev-parse', 'HEAD'))
    with pytest.raises(ValueError, match='Invalid submodule path: ' + path):
        prepare()
    assert not published(tmp_path / 'prepared')


@pytest.mark.parametrize('url', ['file:///etc', 'ext::sh -c id', 'ssh://-oProxyCommand=id/x',
                                 'http://example.com/a.git', '/abs/path', 'git://example.com/a',
                                 'https://user:pw@example.com/a.git', '-u'])
def test_unsupported_submodule_url_is_rejected_before_fetch(unit, tmp_path, monkeypatch, url):
    root, _, _ = unit
    parent, leaf, _, revision = pinned_parent(tmp_path, url)
    fetched, prepare = prepare_parent(root, tmp_path, monkeypatch, parent, leaf, revision)
    with pytest.raises(ValueError, match='Submodule vendor/leaf needs an HTTPS URL') as error:
        prepare()
    assert 'pw' not in str(error.value)
    assert set(fetched) == {'https://example.com/org/parent.git'}
    assert not published(tmp_path / 'prepared')


def test_gitlink_without_gitmodules_is_actionable(unit, tmp_path, monkeypatch):
    root, _, _ = unit
    parent, leaf, _, revision = pinned_parent(tmp_path, gitmodules=False)
    _, prepare = prepare_parent(root, tmp_path, monkeypatch, parent, leaf, revision)
    with pytest.raises(ValueError, match='Missing .gitmodules entry for gitlink vendor/leaf'):
        prepare()


def test_failed_submodule_fetch_names_path_and_url(unit, tmp_path, monkeypatch):
    root, _, _ = unit
    parent, leaf, _, revision = pinned_parent(tmp_path, '../unavailable.git')
    _, prepare = prepare_parent(root, tmp_path, monkeypatch, parent, leaf, revision)
    with pytest.raises(RuntimeError, match='Fetching submodule vendor/leaf from '
                       'https://example.com/org/unavailable.git failed'):
        prepare()


def test_excessively_deep_submodule_tree_is_rejected(tmp_path, monkeypatch):
    sources, revision, url = {}, None, None
    for depth in range(21):
        path = repository(tmp_path / f'r{depth}')
        (path / 'level.txt').write_text(str(depth))
        revision = commit(path)
        if url:
            revision = module(path, 'next', url, revision_below)
        url = f'../r{depth}.git'
        sources[f'https://example.com/org/r{depth}.git'] = path
        revision_below = revision
    serve(monkeypatch, sources)
    spec = git_source_spec('https://example.com/org/r20.git', revision)
    with pytest.raises(ValueError, match='excessively deep submodule tree at ' + '/'.join(['next'] * 20)):
        export_archive(spec, tmp_path / 'cache', lambda: None, lambda text: None)


@pytest.mark.parametrize('kind,error', [('symlink', 'symlinks are not supported'),
                                        ('lfs', 'Git LFS source is not supported')])
def test_runnable_rules_apply_inside_submodules(unit, tmp_path, monkeypatch, kind, error):
    root, _, _ = unit
    def link(path):
        path.symlink_to('value.txt')
    def pointer(path):
        path.write_text('version https://git-lfs.github.com/spec/v1\noid sha256:abc\nsize 1\n')
    files = {'value.txt': lambda path: path.write_text('data'),
             'item': link if kind == 'symlink' else pointer}
    parent, leaf, _, revision = pinned_parent(tmp_path, leaf_files=files)
    _, prepare = prepare_parent(root, tmp_path, monkeypatch, parent, leaf, revision)
    with pytest.raises(ValueError, match=error):
        prepare()
    assert not published(tmp_path / 'prepared')
