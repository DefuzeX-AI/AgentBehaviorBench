"""Safe extraction and completeness checks for ABB-restored source."""
from pathlib import PurePosixPath
import hashlib
import stat
import zipfile


def safe_path(target, name):
    parsed = PurePosixPath(name)
    path = target.joinpath(*parsed.parts)
    if (parsed.is_absolute() or '..' in parsed.parts or '\\' in name or ':' in name
            or not path.resolve().is_relative_to(target.resolve()) or path.is_symlink()):
        raise ValueError('Unsupported path in downloaded source: ' + name)
    return path


def extract_source(archive_path, target, check):
    target.mkdir()
    inventory = {}
    with zipfile.ZipFile(archive_path) as archive:
        for entry in archive.infolist():
            check()
            path = safe_path(target, entry.filename)
            mode = entry.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ValueError('Source symlinks are not supported')
            if entry.is_dir():
                path.mkdir(parents=True, exist_ok=True)
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            with archive.open(entry) as incoming, path.open('xb') as outgoing:
                first = True
                while block := incoming.read(1024 * 1024):
                    check()
                    if first and block.startswith(b'version https://git-lfs.github.com/spec/v1\n'):
                        raise ValueError('Git LFS source is not supported; use bundled source')
                    outgoing.write(block)
                    digest.update(block)
                    first = False
            if mode & 0o111:
                path.chmod(path.stat().st_mode | 0o111)
            inventory[entry.filename] = digest.hexdigest()
    if not inventory:
        raise ValueError('Downloaded Agent source contains no files')
    return inventory


def missing_files(target, inventory, check):
    missing = []
    for name, expected in inventory.items():
        check()
        path = safe_path(target, name)
        if not path.exists():
            missing.append(name)
            continue
        if not path.is_file():
            raise ValueError('Agent source is not a regular file: ' + name)
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            while block := stream.read(1024 * 1024):
                check()
                digest.update(block)
        if digest.hexdigest() != expected:
            raise ValueError('Agent source was modified: ' + name + '; existing files will not be overwritten')
    return missing
