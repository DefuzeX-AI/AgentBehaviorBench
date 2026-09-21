"""Materialize tracked installation inputs without cloning upstream repositories."""
import hashlib
import os
from pathlib import Path
import shutil
import tempfile

from .inventory import missing_files, safe_path


def installation_files(root):
    install = root/'install'
    if install.is_symlink() or not install.resolve().is_relative_to(root.resolve()):
        raise ValueError('install/ must be an unlinked directory inside the Agent unit')
    if not install.is_dir():
        raise FileNotFoundError('Agent installation directory is missing: ' + str(install))
    files = []
    for path in install.rglob('*'):
        if path.is_symlink() or not path.resolve().is_relative_to(install.resolve()):
            raise ValueError('Installation files must not contain symlinks')
        if path.is_file():
            files.append(path)
    if not files:
        raise ValueError('Agent installation directory is empty: ' + str(install))
    return files


def prepare_installation(root, *, check):
    files = installation_files(root)
    target = root/'agent'
    with tempfile.TemporaryDirectory(prefix='.abb-install-', dir=root) as temporary:
        staged = Path(temporary)/'agent'
        staged.mkdir()
        inventory = {}
        for path in files:
            check()
            name = path.relative_to(root/'install').as_posix()
            destination = safe_path(staged, name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            with path.open('rb') as incoming, destination.open('xb') as outgoing:
                while block := incoming.read(1024*1024):
                    check()
                    digest.update(block)
                    outgoing.write(block)
            shutil.copystat(path, destination)
            inventory[name] = digest.hexdigest()
        # A different existing file might be a local edit. Do not overwrite it.
        missing = missing_files(target, inventory, check)
        if not target.exists():
            staged.rename(target)
        else:
            for name in missing:
                check()
                destination = safe_path(target, name)
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.link(staged/name, destination)
        if missing_files(target, inventory, check):
            raise ValueError('Agent installation preparation is incomplete')
        return len(missing), len(inventory)
