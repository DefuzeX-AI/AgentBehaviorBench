"""Safe extraction and completeness checks for ABB-restored source."""
from pathlib import Path, PurePosixPath
import hashlib
import posixpath
import stat
import zipfile


def safe_path(target, name):
    parsed = PurePosixPath(name)
    path = target.joinpath(*parsed.parts)
    if (parsed.is_absolute() or '..' in parsed.parts or '\\' in name or ':' in name
            or not path.resolve().is_relative_to(target.resolve()) or path.is_symlink()):
        raise ValueError('Unsupported path in downloaded source: ' + name)
    return path


def extract_source(archive_path, target, check, *, allow_symlinks=False):
    target.mkdir()
    inventory = {}
    links = {}
    with zipfile.ZipFile(archive_path) as archive:
        for entry in archive.infolist():
            check()
            path = safe_path(target, entry.filename)
            mode = entry.external_attr >> 16
            if stat.S_ISLNK(mode):
                if not allow_symlinks:
                    raise ValueError('Source symlinks are not supported')
                text = archive.read(entry).decode('utf-8')
                if (not text or PurePosixPath(text).is_absolute() or '\\' in text
                        or ':' in text or '\0' in text):
                    raise ValueError('Unsupported source symlink target: ' + entry.filename)
                if entry.filename in links:
                    raise ValueError('Duplicate source symlink: ' + entry.filename)
                links[entry.filename] = text
                continue
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
    pending, completed = set(), set()
    def create_link(name):
        check()
        if name in completed:
            return
        if name in pending:
            raise ValueError('Cyclic source symlink: ' + name)
        pending.add(name)
        text = links[name]
        relative = posixpath.normpath(posixpath.join(posixpath.dirname(name), text))
        if relative == '..' or relative.startswith('../'):
            raise ValueError('Source symlink leaves exported tree: ' + name)
        # Create linked directories/links first so Windows can infer link type.
        for dependency in links:
            if relative == dependency or relative.startswith(dependency + '/'):
                create_link(dependency)
        path = safe_path(target, name)
        destination = (path.parent / text).resolve()
        if not destination.is_relative_to(target.resolve()):
            raise ValueError('Source symlink leaves exported tree: ' + name)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Windows reparse targets require native separators; keep the link relative.
        path.symlink_to(Path(text), target_is_directory=destination.is_dir())
        pending.remove(name)
        completed.add(name)
    for name in links:
        create_link(name)
    if not inventory and not links:
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
