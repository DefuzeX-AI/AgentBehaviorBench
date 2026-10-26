"""Compatibility for historical abb.trajectory.v1 archives only.

No new archives are produced. Historical logical paths resolve through checked
references; explicit recovery can restore their original SDK files.
"""
import hashlib
import io
import json
import os
from copy import deepcopy
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

from agentbench.harness.session.atomic import atomic_bytes, atomic_json

SCHEMA = 'abb.trajectory.v1'


def _safe(root, relative):
    rel = PurePosixPath(str(relative).replace('\\', '/'))
    if rel.is_absolute() or '..' in rel.parts or ':' in str(rel):
        raise ValueError('Artifact reference leaves its root')
    target = root.joinpath(*rel.parts)
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError('Artifact reference leaves its root')
    for part in (target, *target.parents):
        if part == root.parent:
            break
        if part.is_symlink() or (part.exists() and bool(getattr(part.lstat(), 'st_file_attributes', 0) & 0x400)):
            raise ValueError('Linked archive artifact')
    return target


def archive_manifest(root):
    path = Path(root) / 'manifest.json'
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding='utf-8'))
    return value if value.get('schema') == SCHEMA else None


def _encode(value, codec):
    text = json.dumps(value, ensure_ascii=False, indent=2) + codec.get('suffix', '')
    return text.replace('\n', codec.get('newline', '\n')).encode('utf-8')


class ArtifactFile:
    """A bounded read-only logical file; its original bytes retain their digest."""
    def __init__(self, root, relative, manifest):
        self.root, self.relative, self.manifest = root, relative, manifest
        self.name = PurePosixPath(relative).name

    def read_bytes(self, _seen=()):
        if self.relative in _seen or len(_seen) > 20:
            raise ValueError('Cyclic archive reference')
        entry = self.manifest['files'][self.relative]
        if 'projection' in entry:
            projection = entry['projection']
            source = json.loads(ArtifactFile(self.root, projection['source'], self.manifest).read_bytes(
                (*_seen, self.relative)))
            for key in projection['pointer']:
                source = source[key]
            raw = _encode(source, entry['codec'])
        elif entry.get('references'):
            record = json.loads(_safe(self.root, entry['path']).read_bytes())
            value = deepcopy(record['template'])
            for ref in record['references']:
                replacement = json.loads(ArtifactFile(self.root, ref['source'], self.manifest).read_bytes(
                    (*_seen, self.relative)))
                for key in ref.get('pointer', []):
                    replacement = replacement[key]
                parent = value
                for key in ref['target'][:-1]:
                    parent = parent[key]
                parent[ref['target'][-1]] = replacement
            raw = _encode(value, entry['codec'])
        elif 'case_pointer' in entry:
            case_root = self.root.parent.parent
            raw_case = _safe(case_root, 'case.json').read_bytes()
            if hashlib.sha256(raw_case).hexdigest() != entry['case_sha256']:
                raise ValueError('Referenced Case digest mismatch')
            value = json.loads(raw_case)
            for key in entry['case_pointer']:
                value = value[key]
            raw = _encode(value, entry['codec'])
        elif 'capture' in entry:
            value = json.loads(_safe(self.root, entry['capture']).read_bytes())[entry['key']]
            raw = _encode(value, entry['codec'])
        elif 'document' in entry:
            value = self.manifest['documents'][entry['document']]
            raw = _encode(value, entry['codec'])
        else:
            with _safe(self.root, entry['path']).open('rb') as stream:
                if 'offset' not in entry and os.fstat(stream.fileno()).st_size != entry['size']:
                    raise ValueError('Archived evidence digest mismatch: ' + self.relative)
                stream.seek(entry.get('offset', 0))
                raw = stream.read(entry['size'])
        if len(raw) != entry['size'] or hashlib.sha256(raw).hexdigest() != entry['sha256']:
            raise ValueError('Archived evidence digest mismatch: ' + self.relative)
        return raw

    def read_text(self, encoding='utf-8', **kwargs):
        return self.read_bytes().decode(encoding)

    def open(self, mode='r', encoding=None, **kwargs):
        if mode not in ('r', 'rb'):
            raise ValueError('Archived artifacts are read-only')
        data = self.read_bytes()
        return io.BytesIO(data) if mode == 'rb' else io.StringIO(data.decode(encoding or 'utf-8'))

    def stat(self):
        original = (self.root / 'manifest.json').stat()
        return SimpleNamespace(st_size=self.manifest['files'][self.relative]['size'],
            st_mtime=original.st_mtime, st_mtime_ns=original.st_mtime_ns,
            st_ctime_ns=original.st_ctime_ns)

    def is_file(self):
        return True

    def is_dir(self):
        return False

    def exists(self):
        return True

    def is_symlink(self):
        return False


def artifact_file(directory, relative):
    root = Path(directory).resolve()
    relative = str(relative).replace('\\', '/')
    candidate = _safe(root, relative)
    manifest = archive_manifest(root)
    if manifest and relative in manifest['files']:
        return ArtifactFile(root, relative, manifest)
    if manifest and relative == 'evaluation/inputs':
        return root / 'steps'
    if not candidate.exists():
        raise FileNotFoundError(candidate)
    return candidate


def resolve_artifact_path(path):
    """Adapt SDK readers that already hold a complete logical artifact path."""
    path = Path(path)
    for root in path.parents:
        if root.parent.name == 'trajectory' and archive_manifest(root):
            return artifact_file(root, path.relative_to(root).as_posix())
    return path


def restore_archive(directory):
    """Explicit write boundary for later Judge operations, never used by viewers."""
    root = Path(directory).resolve()
    manifest = archive_manifest(root)
    if not manifest:
        return
    originals = {relative: ArtifactFile(root, relative, manifest).read_bytes() for relative in manifest['files']}
    for relative, raw in originals.items():
        atomic_bytes(_safe(root, relative), raw)
    # All legacy documents are durable before switching readers back to them.
    (root / 'manifest.json').unlink()
    for entry in manifest['files'].values():
        canonical = entry.get('path') or entry.get('capture')
        if canonical and canonical not in originals:
            _safe(root, canonical).unlink(missing_ok=True)
