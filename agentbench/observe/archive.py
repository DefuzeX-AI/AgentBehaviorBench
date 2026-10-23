"""Lossless trajectory archives and read-only compatibility views.

Runtime producers keep their private contracts. Once execution and judging end,
publish a compact manifest before retiring transport copies. Legacy logical paths
resolve through checked references; readers never recreate files on disk.
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


def _codec(raw, value):
    for newline in ('\n', '\r\n'):
        for suffix in ('', '\n'):
            codec = {'newline': newline, 'suffix': suffix}
            if _encode(value, codec) == raw:
                return codec
    return None


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


def _project(root, manifest, source, pointer, target, value):
    """Replace a derived file only if reconstructing it preserves exact bytes."""
    if target not in manifest['files'] or source not in manifest['files']:
        return
    raw = ArtifactFile(root, target, manifest).read_bytes()
    codec = _codec(raw, value)
    if codec is not None and json.loads(raw) == value:
        manifest['files'][target] = {'projection': {'source': source, 'pointer': pointer},
            'codec': codec, 'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


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


def compact_trajectory(directory):
    root = Path(directory).resolve()
    if root.parent.name != 'trajectory' or archive_manifest(root):
        return
    pending = root / '.archive-pending.json'
    if pending.is_file():
        # A failed packing attempt may have published staging copies, but its
        # originals were not retired. Remove only files absent from that inventory.
        originals = set(json.loads(pending.read_bytes())['sources'])
        for path in list(root.rglob('*')):
            relative = path.relative_to(root).as_posix()
            if path.is_file() and relative not in originals and path != pending:
                _safe(root, relative).unlink()
        pending.unlink()
    host_path = root / 'run.json'
    summary_path = root / 'evaluation/manifest.json'
    if not host_path.is_file() or not summary_path.is_file():
        return
    host = json.loads(host_path.read_text(encoding='utf-8'))
    summary = json.loads(summary_path.read_text(encoding='utf-8'))
    # Interrupted work keeps its original recovery and transport state intact.
    if (host.get('cleanup_status') != 'succeeded' or host.get('host_trace_validation') != 'succeeded'
            or not ((root / 'evaluation/judge/report.json').is_file()
                    or summary.get('judge_delivery_status') == 'not_requested')):
        return
    sources = {p.relative_to(root).as_posix(): p for p in root.rglob('*') if p.is_file()}
    atomic_json(pending, {'schema': 'abb.archive-pending.v1', 'sources': list(sources)})
    documents, entries, retained = {}, {}, set()
    manifest = {'schema': SCHEMA, 'agent_id': host.get('agent_id'),
        'case_id': host.get('case_id'), 'trajectory_id': root.name,
        'documents': documents, 'files': entries}
    blobs = {}
    captures = {}

    for relative, source in sources.items():
        _safe(root, relative)
        # Communication is consumed and validated before this terminal archive.
        if relative.startswith(('channel/', 'agent-output/', 'agent-request/')):
            continue
        raw = source.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        entry = {'sha256': digest, 'size': len(raw)}
        canonical = relative
        if relative.startswith('evaluation/inputs/'):
            canonical = 'steps/' + relative[len('evaluation/inputs/'):]
            canonical = canonical.replace('/request.json', '/invocation.json')
        elif relative.startswith('evaluation/judge/'):
            canonical = 'judge/' + relative[len('evaluation/judge/'):]
        elif relative == 'judge-task.json':
            canonical = 'judge/task.json'
        elif relative.startswith(('sdk-repo/', 'judge-state/')):
            # SDK paths can already approach MAX_PATH on Windows. Flatten their
            # physical archive names; the index preserves the native ledger tree.
            canonical = 'sdk-state/' + digest[:32] + source.suffix
        elif relative in ('network.jsonl', 'egress.jsonl') or relative.startswith('timing'):
            canonical = 'logs/' + relative
        elif relative == 'agent-runtime/egress.jsonl':
            canonical = 'logs/agent-egress.jsonl'

        # Consolidate small metadata without changing its original serialized bytes.
        metadata = (relative.endswith('.json') and not relative.startswith(
            ('evaluation/inputs/', 'evaluation/judge/', 'sdk-repo/', 'judge-state/', 'replay/')))
        value = None
        if metadata:
            try:
                value = json.loads(raw)
            except (ValueError, UnicodeError):
                pass
        codec = _codec(raw, value) if metadata and value is not None else None
        capture_names = {'otel-status.json', 'capture-status.json', 'result-redaction.json', 'context.json'}
        if relative.startswith('evaluation/inputs/') and source.name in capture_names:
            value = json.loads(raw)
            codec = _codec(raw, value)
            if codec is not None:
                step = relative.split('/')[2]
                capture = captures.setdefault(step, {})
                capture[source.name] = value
                entry.update(capture=f'steps/{step}/capture.json', key=source.name, codec=codec)
        if 'capture' in entry:
            pass
        elif codec is not None:
            documents[relative] = value
            entry.update(document=relative, codec=codec)
        else:
            # Payloads are content-addressed; identical content is stored only once.
            if '/otel-payloads/' in relative:
                canonical = 'blobs/' + digest
            if digest in blobs:
                canonical = blobs[digest]
            target = _safe(root, canonical)
            if target != source:
                atomic_bytes(target, raw)
            blobs[digest] = canonical
            retained.add(canonical)
            entry['path'] = canonical
        entries[relative] = entry

    for step, capture in captures.items():
        atomic_json(root / 'steps' / step / 'capture.json', capture)

    # The selected Case already exists outside this trajectory. Link its exact
    # data instead of retaining evaluation and SDK copies of the same Case.
    case_file = root.parent.parent / 'case.json'
    if case_file.is_file() and 'evaluation/case.json' in entries:
        raw_case = case_file.read_bytes()
        saved = json.loads(raw_case)
        raw = ArtifactFile(root, 'evaluation/case.json', manifest).read_bytes()
        value = json.loads(raw)
        pointer = [] if saved == value else ['case'] if saved.get('case') == value else None
        codec = _codec(raw, value)
        if pointer is not None and codec is not None:
            entries['evaluation/case.json'] = {'case_pointer': pointer,
                'case_sha256': hashlib.sha256(raw_case).hexdigest(), 'codec': codec,
                'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw)}
            documents.pop('evaluation/case.json', None)

    for folder in sorted((root / 'evaluation/inputs').glob('*')):
        prefix = folder.relative_to(root).as_posix()
        source = prefix + '/submission.json'
        if source not in entries:
            continue
        submission = json.loads(ArtifactFile(root, source, manifest).read_bytes())
        evidence = submission.get('extensions', {}).get('trace_evidence')
        if evidence is not None:
            _project(root, manifest, source, ['extensions', 'trace_evidence'], prefix + '/evidence.json', evidence)
        item_name = prefix + '/input.json'
        if item_name in entries:
            item = json.loads(ArtifactFile(root, item_name, manifest).read_bytes())
            _project(root, manifest, item_name, ['payload'], prefix + '/mapped-input.json', item.get('payload'))

    context_name = 'evaluation/judge/context.json'
    if context_name in entries:
        raw = ArtifactFile(root, context_name, manifest).read_bytes()
        context = json.loads(raw)
        codec = _codec(raw, context)
        refs = []
        if codec is not None and isinstance(context.get('history'), list):
            template = deepcopy(context)
            if 'evaluation/case.json' in entries and context.get('case') == json.loads(
                    ArtifactFile(root, 'evaluation/case.json', manifest).read_bytes()):
                template['case'] = None
                refs.append({'target': ['case'], 'source': 'evaluation/case.json'})
            for index, item in enumerate(context['history']):
                for field, name in (('submission', 'submission'), ('test_input', 'input')):
                    source = f'evaluation/inputs/{index+1:04d}/{name}.json'
                    if source in entries and item.get(field) == json.loads(ArtifactFile(root, source, manifest).read_bytes()):
                        template['history'][index][field] = None
                        refs.append({'target': ['history', index, field], 'source': source})
            if refs:
                canonical = 'judge/context.json'
                atomic_json(root / canonical, {'schema': 'abb.reference-document.v1',
                    'template': template, 'references': refs})
                entries[context_name] = {'path': canonical, 'references': True, 'codec': codec,
                    'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

    # Put timing streams in one file; byte ranges keep their exact legacy view.
    timing = [(name, ArtifactFile(root, name, manifest).read_bytes()) for name in entries
              if 'timing' in name and name.endswith('.jsonl')]
    if timing:
        offset, combined = 0, bytearray()
        for name, raw in timing:
            entries[name] = {**entries[name], 'path': 'logs/timing.jsonl', 'offset': offset}
            combined.extend(raw)
            offset += len(raw)
        atomic_bytes(root / 'logs/timing.jsonl', bytes(combined))

    # Commit the reference map before removing any original file. Verify every
    # reconstruction first, including all metadata and content-addressed blobs.
    for relative in entries:
        ArtifactFile(root, relative, manifest).read_bytes()
    atomic_json(root / 'manifest.json', manifest)
    retained = ({entry['path'] for entry in entries.values() if 'path' in entry}
                | {entry['capture'] for entry in entries.values() if 'capture' in entry} | {'manifest.json'})
    for source in list(root.rglob('*')):
        if source.is_file() and source.relative_to(root).as_posix() not in retained:
            _safe(root, source.relative_to(root).as_posix()).unlink(missing_ok=True)
    for folder in sorted((p for p in root.rglob('*') if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        if not any(folder.iterdir()):
            folder.rmdir()


def compact_suite(directory):
    from agentbench.harness.session import read_suite
    from agentbench.harness.session.references import _event_paths
    root = Path(directory)
    plan, events = read_suite(root)
    if plan.get('artifact_layout') != 'agent-trajectories-v1':
        return
    paths = {p for event in events for p in _event_paths(event) if p.is_dir() and p.parent.name == 'trajectory'}
    for path in sorted(paths):
        compact_trajectory(path)
