"""Complete commit archives, including commit-pinned submodule trees."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
from urllib.parse import urljoin
import zipfile

from .cache import cache_lock, source_archive
from .config import git_source_spec
from . import git as acquisition


def _relative(name):
    path = PurePosixPath(name)
    if (not path.parts or path.is_absolute() or '..' in path.parts
            or '\\' in name or ':' in name or str(path) != name):
        raise ValueError('Invalid submodule path: ' + name)
    return name


def _label(where, name):
    return where + '/' + name if where else name


def _repository(parent, value):
    match = re.fullmatch(r'git@([A-Za-z0-9.-]+):(.+)', value)
    if match:
        value = 'https://' + match[1] + '/' + match[2]
    elif value.startswith(('./', '../')):
        value = urljoin(parent.rstrip('/') + '/', value)
    return value


def _archive(spec, output, check, output_fn, ancestors=(), where=''):
    identity = (spec.repository, spec.revision)
    if identity in ancestors or len(ancestors) >= 20:
        raise ValueError('Cyclic or excessively deep submodule tree at ' + (where or '.'))
    with tempfile.TemporaryDirectory(prefix='abb-export-git-') as temporary:
        directory = Path(temporary)
        acquisition.run_git(directory, ['init', '--bare', '--quiet'], check)
        output_fn('Export source: ' + spec.repository + ' @ ' + spec.revision)
        try:
            acquisition.run_git(directory, ['fetch', '--quiet', '--depth=1', '--no-tags', '--',
                                spec.repository, spec.revision], check)
        except RuntimeError as error:
            if not where:
                raise
            raise RuntimeError(f'Fetching submodule {where} from {spec.repository} failed') from error
        actual = acquisition.run_git(directory, ['rev-parse', 'FETCH_HEAD^{commit}'], check).strip()
        if actual != spec.revision:
            raise ValueError('Downloaded source commit does not match requested revision')
        tree = acquisition.run_git(directory, ['ls-tree', '-rz', actual], check)
        links, names = {}, set()
        for item in tree.split('\0'):
            if not item:
                continue
            metadata, name = item.split('\t', 1)
            mode, kind, sha = metadata.split()
            names.add(name)
            if mode == '160000':
                links[_relative(name)] = sha
        modules = {}
        if links and '.gitmodules' not in names:
            raise ValueError('Missing .gitmodules entry for gitlink ' + _label(where, min(links)))
        if links:
            config = acquisition.run_git(directory, ['config', '--null', '--blob', actual + ':.gitmodules',
                             '--list'], check)
            sections = {}
            for item in config.split('\0'):
                if not re.fullmatch(r'submodule\..*\.(path|url)\n.*', item, re.S):
                    continue
                key, value = item.split('\n', 1)
                section, field = key.rsplit('.', 1)
                if field in sections.setdefault(section, {}):
                    raise ValueError('Duplicate submodule configuration: ' + key)
                sections[section][field] = value
            for entry in sections.values():
                name = _relative(entry.get('path', ''))
                if name in modules:
                    raise ValueError('Duplicate submodule path: ' + name)
                modules[name] = entry.get('url', '')
        # Validate every gitlink before fetching any submodule.
        children = {}
        for name, revision in sorted(links.items()):
            if name not in modules:
                raise ValueError('Missing .gitmodules entry for gitlink ' + _label(where, name))
            try:
                children[name] = git_source_spec(_repository(spec.repository, modules[name]), revision)
            except ValueError as error:
                raise ValueError('Submodule ' + _label(where, name)
                                 + ' needs an HTTPS URL without credentials') from error
        own = directory / 'own.zip'
        acquisition.run_git(directory, ['archive', '--format=zip', '--output=' + str(own), actual], check)
        records = []
        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as merged:
            with zipfile.ZipFile(own) as source:
                for entry in source.infolist():
                    check()
                    if entry.filename.rstrip('/') in links:
                        continue
                    with source.open(entry) as incoming, merged.open(entry, 'w') as outgoing:
                        shutil.copyfileobj(incoming, outgoing)
            for index, (name, child) in enumerate(children.items()):
                archive = directory / f'child-{index}.zip'
                nested = _archive(child, archive, check, output_fn, (*ancestors, identity),
                                  _label(where, name))
                records.append({'path': name, 'repository': child.repository, 'revision': child.revision})
                records.extend({**record, 'path': name + '/' + record['path']} for record in nested)
                with zipfile.ZipFile(archive) as source:
                    for entry in source.infolist():
                        check()
                        with source.open(entry) as incoming:
                            entry.filename = name + '/' + entry.filename
                            with merged.open(entry, 'w') as outgoing:
                                shutil.copyfileobj(incoming, outgoing)
            merged.comment = spec.revision.encode('ascii')
        return records


def _expanded(path):
    try:
        return bool(json.loads(path.read_text(encoding='utf-8'))['submodules'])
    except (OSError, ValueError, KeyError, TypeError):
        return False


def export_archive(spec, directory, check, output_fn=print):
    """Return a verified commit archive and its pinned submodule records.

    Trees without gitlinks keep the regular commit archive and cache entry, so
    those archives stay byte-identical. Only trees with gitlinks are expanded
    recursively, into a separate cache.
    """
    directory = Path(directory).resolve()
    key = hashlib.sha256((spec.repository + '\n' + spec.revision).encode()).hexdigest()
    # The legacy producer only publishes archives without any submodules.
    if (directory / (key + '.zip')).is_file():
        return source_archive(spec, directory, check, output_fn), []
    # Older recursive entries without submodules yield to the regular archive.
    if not _expanded(directory / 'recursive-v1' / (key + '.json')):
        try:
            return source_archive(spec, directory, check, output_fn), []
        except acquisition.SubmoduleSource:
            output_fn('Source contains submodules: exporting pinned submodule commits')
    directory = directory / 'recursive-v1'
    directory.mkdir(parents=True, exist_ok=True)
    target, metadata = directory / (key + '.zip'), directory / (key + '.json')
    with cache_lock(directory / (key + '.lock'), check):
        if not target.is_file():
            with tempfile.TemporaryDirectory(prefix='.export-', dir=directory) as temporary:
                staged = Path(temporary) / 'source.zip'
                modules = _archive(spec, staged, check, output_fn)
                with zipfile.ZipFile(staged) as archive:
                    if archive.comment.decode('ascii') != spec.revision or archive.testzip() is not None:
                        raise ValueError('Invalid recursive source archive')
                details = Path(temporary) / 'source.json'
                details.write_text(json.dumps({'repository': spec.repository, 'revision': spec.revision,
                    'archive_sha256': hashlib.sha256(staged.read_bytes()).hexdigest(),
                    'submodules': modules}, indent=2), encoding='utf-8')
                os.replace(details, metadata)
                os.replace(staged, target)
        details = json.loads(metadata.read_text(encoding='utf-8'))
        if (details['repository'] != spec.repository or details['revision'] != spec.revision
                or hashlib.sha256(target.read_bytes()).hexdigest() != details['archive_sha256']):
            raise ValueError('Recursive source cache provenance mismatch')
        return target, details['submodules']


def export_digest(root):
    """Hash all exported paths, file bytes and link text without following links."""
    root = Path(root)
    digest = hashlib.sha256(b'abb.export-tree.v1\0')
    def add(value):
        digest.update(len(value).to_bytes(8, 'big'))
        digest.update(value)
    for directory, folders, files in os.walk(root, followlinks=False):
        folders.sort()
        for name in sorted(folders + files):
            path = Path(directory) / name
            add(path.relative_to(root).as_posix().encode('utf-8'))
            if path.is_symlink():
                add(b'link')
                add(os.readlink(path).encode('utf-8'))
            elif path.is_dir():
                add(b'directory')
            else:
                add(b'file')
                digest.update(path.stat().st_size.to_bytes(8, 'big'))
                with path.open('rb') as stream:
                    while block := stream.read(1024 * 1024):
                        digest.update(block)
    return digest.hexdigest()
