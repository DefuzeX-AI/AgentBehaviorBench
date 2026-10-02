"""Lazy, read-only browsing of files inside an already authorized result run."""
import json
import os
import stat
from pathlib import Path, PurePosixPath

PAGE_SIZE = 200
PREVIEW_BYTES = 1024 * 1024


def _linked(info):
    # Junctions are reparse points on Windows, even when is_symlink() is false.
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)


def result_path(directory, relative=''):
    root = Path(directory).resolve(strict=True)
    path = PurePosixPath(relative)
    if (not isinstance(relative, str) or '\\' in relative or ':' in relative
            or path.is_absolute() or '..' in path.parts
            or (relative and path.as_posix() != relative)):
        raise ValueError('Invalid result path')
    target = root
    for part in path.parts:
        target = target / part
        if _linked(target.lstat()):
            raise ValueError('Linked files are not browsable')
    resolved = target.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise ValueError('File outside result directory')
    return resolved


def list_files(directory, relative='', offset=0):
    target = result_path(directory, relative)
    if not target.is_dir() or offset < 0:
        raise ValueError('Invalid directory or cursor')
    entries = []
    with os.scandir(target) as children:
        for child in children:
            try:
                info = child.stat(follow_symlinks=False)
                if _linked(info) or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                    continue
                entries.append({'name': child.name,
                                'path': f'{relative}/{child.name}' if relative else child.name,
                                'type': 'directory' if stat.S_ISDIR(info.st_mode) else 'file',
                                'size': info.st_size if stat.S_ISREG(info.st_mode) else None})
            except OSError:
                continue
    entries.sort(key=lambda row: (row['type'] != 'directory', row['name'].casefold(), row['name']))
    end = offset + PAGE_SIZE
    return {'path': relative, 'entries': entries[offset:end], 'total': len(entries),
            'next': end if end < len(entries) else None}


def preview_file(directory, relative):
    target = result_path(directory, relative)
    if not target.is_file():
        raise ValueError('Not a result file')
    with target.open('rb') as stream:
        size = os.fstat(stream.fileno()).st_size
        content = stream.read(PREVIEW_BYTES + 1)
    truncated = len(content) > PREVIEW_BYTES
    content = content[:PREVIEW_BYTES]
    text = None
    if b'\x00' not in content:
        try:
            # An incomplete final UTF-8 character at the preview boundary is omitted.
            import codecs
            text = codecs.getincrementaldecoder('utf-8')().decode(content, final=not truncated)
        except UnicodeDecodeError:
            pass
    return {'path': relative, 'size': size, 'text': text, 'binary': text is None,
            'truncated': truncated, 'preview_bytes': min(size, PREVIEW_BYTES)}


def read_json(directory, relative):
    try:
        file = preview_file(directory, relative)
    except FileNotFoundError:
        return None
    if file['binary'] or file['truncated']:
        raise ValueError('JSON artifact is not a complete UTF-8 document')
    return json.loads(file['text'])


if __name__ == '__main__':
    import sys
    query = json.loads(sys.argv[2])
    value = (preview_file(sys.argv[1], query['path']) if query.get('operation') == 'file'
             else list_files(sys.argv[1], query.get('path', ''), int(query.get('offset', 0))))
    print(json.dumps(value, ensure_ascii=True))
