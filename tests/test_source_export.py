"""Source-only exports preserve links and recursively pinned Git submodules."""
from pathlib import Path
import stat
import zipfile

import pytest

from agentbench.runtime.source import git as acquisition
from agentbench.runtime.source.config import git_source_spec
from agentbench.runtime.source.export import export_archive, export_digest
from agentbench.runtime.source.inventory import extract_source
from tests.test_runtime_source import git


def repository(path):
    path.mkdir()
    git(path, 'init', '-q')
    git(path, 'config', 'user.email', 'test@example.com')
    git(path, 'config', 'user.name', 'Test')
    return path


def commit(path):
    git(path, 'add', '.')
    git(path, 'commit', '-qm', 'snapshot')
    return git(path, 'rev-parse', 'HEAD')


def module(path, name, url, revision):
    (path / '.gitmodules').write_text(
        f'[submodule "dependency"]\npath = {name}\nurl = {url}\nbranch = main\n')
    git(path, 'add', '.gitmodules')
    git(path, 'update-index', '--add', '--cacheinfo', f'160000,{revision},{name}')
    git(path, 'commit', '-qm', 'pin dependency')
    return git(path, 'rev-parse', 'HEAD')


def test_recursive_export_uses_gitlink_commits_and_cache(tmp_path, monkeypatch):
    leaf = repository(tmp_path / 'leaf')
    (leaf / 'value.txt').write_text('pinned version')
    pinned = commit(leaf)
    (leaf / 'value.txt').write_text('new branch version')
    commit(leaf)
    child = repository(tmp_path / 'child')
    child_sha = module(child, 'vendor/leaf', '../leaf.git', pinned)
    parent = repository(tmp_path / 'parent')
    revision = module(parent, 'deps/child', 'git@example.com:org/child.git', child_sha)
    sources = {f'https://example.com/org/{name}.git': path
               for name, path in [('parent', parent), ('child', child), ('leaf', leaf)]}
    original = acquisition.run_git
    fetched = []
    def fetch_local(directory, args, check):
        if args[0] == 'fetch':
            fetched.append((args[-2], args[-1]))
            args = ['-c', 'protocol.file.allow=always', *args[:-2], str(sources[args[-2]]), args[-1]]
        return original(directory, args, check)
    monkeypatch.setattr(acquisition, 'run_git', fetch_local)
    spec = git_source_spec('https://example.com/org/parent.git', revision)
    archive, modules = export_archive(spec, tmp_path / 'cache', lambda: None)
    target = tmp_path / 'out'
    extract_source(archive, target, lambda: None, allow_symlinks=True)
    assert (target / 'deps/child/vendor/leaf/value.txt').read_text() == 'pinned version'
    assert [(r['path'], r['revision']) for r in modules] == [
        ('deps/child', child_sha), ('deps/child/vendor/leaf', pinned)]
    assert len(fetched) == 3
    assert export_archive(spec, tmp_path / 'cache', lambda: None) == (archive, modules)
    assert len(fetched) == 3


def link_archive(path, links, files=None):
    with zipfile.ZipFile(path, 'w') as archive:
        for name, text in links.items():
            entry = zipfile.ZipInfo(name)
            entry.create_system = 3
            entry.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(entry, text)
        for name, text in (files or {}).items():
            archive.writestr(name, text)


def test_export_preserves_file_directory_and_broken_links(tmp_path):
    archive = tmp_path / 'links.zip'
    links = {'docs/license': '../LICENSE', 'alias': 'directory', 'directory': 'real',
             'missing': 'not-present'}
    link_archive(archive, links, {'LICENSE': 'terms', 'real/value': 'content'})
    out = tmp_path / 'out'
    extract_source(archive, out, lambda: None, allow_symlinks=True)
    assert all((out / name).is_symlink() for name in links)
    assert (out / 'docs/license').read_text() == 'terms'
    assert (out / 'alias/value').read_text() == 'content'
    before = export_digest(out)
    (out / 'missing').unlink()
    (out / 'missing').symlink_to('other-missing')
    assert export_digest(out) != before
    with pytest.raises(ValueError, match='symlinks are not supported'):
        extract_source(archive, tmp_path / 'runtime', lambda: None)


@pytest.mark.parametrize('links', [
    {'escape': '../outside'}, {'escape': '/outside'},
    {'a': 'b', 'b': 'a'}, {'a': 'dir/../../outside'},
    {'dir': 'safe', 'escape': 'dir/../../outside'},
])
def test_export_rejects_escaping_or_cyclic_links(tmp_path, links):
    archive = tmp_path / 'unsafe.zip'
    link_archive(archive, links, {'safe/value': 'data'})
    with pytest.raises(ValueError):
        extract_source(archive, tmp_path / 'out', lambda: None, allow_symlinks=True)
    assert not (tmp_path / 'outside').exists()
