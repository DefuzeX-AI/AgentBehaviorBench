"""Read canonical execution artifacts, with fallbacks for historical results.

New producers write ordinary files in the final tree. These aliases are only a
reader compatibility boundary; there is no post-run packing or unpacking.
"""
from pathlib import Path, PurePosixPath


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
            raise ValueError('Linked artifact')
    return target


def canonical_relative(relative):
    relative = str(relative).replace('\\', '/')
    if relative.startswith('inputs/'):
        return 'steps/' + relative[len('inputs/'):]
    if relative == 'evaluation/inputs':
        return 'steps'
    if relative.startswith('evaluation/inputs/'):
        return 'steps/' + relative[len('evaluation/inputs/'):]
    if relative.startswith('evaluation/'):
        return canonical_relative(relative[len('evaluation/'):])
    if relative in ('network.jsonl', 'sdk.jsonl'):
        return 'logs/' + relative
    return relative


def legacy_relative(relative):
    relative = canonical_relative(relative)
    if relative in ('logs/network.jsonl', 'logs/sdk.jsonl'):
        return relative[5:] if relative.endswith('network.jsonl') else 'evaluation/sdk.jsonl'
    if relative == 'steps':
        return 'evaluation/inputs'
    if relative.startswith('steps/'):
        return 'evaluation/inputs/' + relative[len('steps/'):]
    if relative.startswith(('judge/', 'cases/', 'prepared-cases/', 'workspace-files/', 'recovery/')):
        return 'evaluation/' + relative
    if relative in {'manifest.json', 'case.json', 'case-selection.json', 'case-collection.json',
                    'error.json', 'process.json', 'session.json', 'termination.json',
                    'workspace.json', 'workspace-artifacts.json', 'agent-context.json', 'sdk.jsonl'}:
        return 'evaluation/' + relative
    return relative


def artifact_file(directory, relative):
    root = Path(directory).resolve()
    _safe(root, relative)
    canonical = canonical_relative(relative)
    for name in dict.fromkeys((canonical, str(relative), legacy_relative(canonical))):
        candidate = _safe(root, name)
        if candidate.exists():
            return candidate
    raise FileNotFoundError(root / canonical)


def resolve_artifact_path(path):
    path = Path(path)
    for root in path.parents:
        if (root / 'run.json').is_file() or (root / 'evaluation/manifest.json').is_file():
            return artifact_file(root, path.relative_to(root).as_posix())
    return path
