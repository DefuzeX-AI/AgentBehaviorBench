"""Read only the local replay archive; shared by the Python and Vite viewers."""
import json
import re
import os
import stat
from pathlib import Path, PurePosixPath

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




MAX_JSON_BYTES = 16 * 1024 * 1024


def _json(directory, name):
    try:
        path = result_path(directory, 'replay/' + name)
    except FileNotFoundError:
        return None
    if path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError('Replay record exceeds the read limit')
    return json.loads(path.read_text(encoding='utf-8'))


def replay(directory, query):
    def arg(key, default=''):
        value = query.get(key, default)
        return value[0] if isinstance(value, list) else value
    digest = arg('blob')
    if digest:
        if not re.fullmatch(r'[0-9a-f]{64}', digest):
            raise ValueError('Invalid replay content ID')
        return preview_file(directory, 'replay/blobs/' + digest)
    offset = int(arg('offset', '0'))
    if offset < 0:
        raise ValueError('Invalid replay cursor')
    manifest = _json(directory, 'manifest.json')
    error = _json(directory, 'capture-error.json')
    if manifest is None:
        return {'available': False, 'events': [], 'next': None,
                'warnings': [error['message']] if error else []}
    warnings = list(manifest.get('warnings', []))
    through = min(int(arg('through', str(manifest.get('event_count', 0)))), manifest.get('event_count', 0))
    if through < 0:
        raise ValueError('Invalid replay version')
    if error:
        warnings.append(error['message'])
    if manifest.get('status') == 'recording':
        metadata = json.loads(result_path(directory, 'run.json').read_text(encoding='utf-8'))
        if metadata.get('status') not in ('running', 'queued'):
            warnings.append('Recording did not finish; the last captured version may be incomplete.')
    events, next_offset = [], None
    try:
        path = result_path(directory, 'replay/events.jsonl')
        with path.open(encoding='utf-8') as stream:
            index = 0
            while line := stream.readline(MAX_JSON_BYTES + 1):
                if len(line) > MAX_JSON_BYTES:
                    raise ValueError('Replay event exceeds the read limit')
                if index < offset:
                    index += 1
                    continue
                if len(events) == 100:
                    next_offset = index
                    break
                index += 1
                try:
                    row = json.loads(line)
                    if not isinstance(row.get('time_ms'), (int, float)) or not isinstance(row.get('changes'), list):
                        raise ValueError('Invalid event')
                    if row.get('sequence', 0) > through:
                        break
                    events.append(row)
                except (ValueError, TypeError, AttributeError):
                    warnings.append('Incomplete or invalid replay event; file history may have a gap.')
    except FileNotFoundError:
        pass
    return {'available': True, 'manifest': manifest,
            'baseline': _json(directory, 'baseline.json') if offset == 0 else None,
            'events': events, 'next': next_offset, 'warnings': list(dict.fromkeys(warnings))}


if __name__ == '__main__':
    import sys
    print(json.dumps(replay(Path(sys.argv[1]), json.loads(sys.argv[2]) if len(sys.argv) > 2 else {})))
