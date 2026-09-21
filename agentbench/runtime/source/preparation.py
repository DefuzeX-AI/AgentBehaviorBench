"""Restore missing Agent source before opening an evaluation SDK."""
from pathlib import Path
import hashlib
import json
import os
import tempfile
import time

from agentbench.runtime.agentcontainer.config import tomllib, docker_structure
from .config import source_spec, InstallSource
from .cache import cache_lock, source_archive
from .inventory import extract_source, missing_files


def prepare_agent_source(root, *, check=lambda: None, cache_dir=None, output_fn=lambda text: None):
    root = Path(root).resolve()
    check()
    output_fn('Checking Agent files')
    manifest = tomllib.loads((root/'agent.toml').read_text(encoding='utf-8'))
    spec = source_spec(manifest)
    if manifest.get('runtime', {}).get('type') == 'docker':
        docker_structure(root, manifest)
    if not (root/'requirement.md').is_file():
        raise FileNotFoundError('Agent requirement.md is missing: ' + str(root))
    target = root/'agent'
    if target.is_symlink() or not target.resolve().is_relative_to(root):
        raise ValueError('Agent source must be an unlinked directory inside its unit')
    if target.exists() and not target.is_dir():
        raise ValueError('Agent source path is not a directory: ' + str(target))
    if spec is None:
        if not target.is_dir():
            raise FileNotFoundError('Bundled Agent source is missing: ' + str(target))
        output_fn('Agent source: reused local files .... OK')
        return
    if manifest.get('build', {}).get('context') != '.':
        raise ValueError('Source preparation currently requires build.context="."')
    if cache_dir is None:
        from agentbench.project import project_root
        cache_dir = project_root()/'cache/sources'
    cache_dir = Path(cache_dir).resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(str(root).encode()).hexdigest()
    record_path = cache_dir/(key + '.state.json')
    end = time.monotonic() + 300
    def bounded_check():
        check()
        if time.monotonic() >= end:
            raise TimeoutError('Agent source preparation exceeded 300 seconds')
    with cache_lock(cache_dir/(key + '.unit.lock'), bounded_check):
        if isinstance(spec, InstallSource):
            from .installation import prepare_installation
            output_fn('Installation inputs: checking install/ -> agent/')
            copied, total = prepare_installation(root, check=bounded_check)
            action = f'copied {copied}/{total} files' if copied else f'reused {total} files'
            output_fn('Installation inputs: ' + action + ' .... OK')
            return
        record = json.loads(record_path.read_text(encoding='utf-8')) if record_path.exists() else None
        if record and (record['repository'], record['revision']) != (spec.repository, spec.revision):
            if target.exists() and any(target.iterdir()):
                raise ValueError('source.revision changed; move existing agent/ aside before restoring')
            record = None
        if record:
            if not missing_files(target, record['files'], bounded_check):
                output_fn('Agent source: verified existing files .... OK')
                return
        elif target.is_dir() and any(target.iterdir()):
            output_fn('Agent source: reused local files (unmanaged) .... OK')
            return
        output_fn('Restoring Agent source: ' + spec.repository + ' @ ' + spec.revision)
        archive = source_archive(spec, cache_dir, bounded_check, output_fn)
        with tempfile.TemporaryDirectory(prefix='.abb-source-', dir=root) as temporary:
            staged = Path(temporary)/'agent'
            inventory = extract_source(archive, staged, bounded_check)
            missing = missing_files(target, inventory, bounded_check)
            # Publish inventory first so an interrupted installation is repairable.
            state = cache_dir/(key + '.state.tmp')
            state.write_text(json.dumps({'repository': spec.repository, 'revision': spec.revision,
                                         'files': inventory}), encoding='utf-8')
            os.replace(state, record_path)
            if not target.exists():
                staged.rename(target)
            else:
                for name in missing:
                    bounded_check()
                    destination = target/name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    # The staged files are on the same volume. Hard-link creation
                    # is atomic and fails if another process has created the file.
                    os.link(staged/name, destination)
            if missing_files(target, inventory, bounded_check):
                raise ValueError('Agent source restoration is incomplete')
        output_fn(f'Agent source: restored {len(missing)} files and verified .... OK')
