"""Read canonical execution artifacts, with fallbacks for historical results.

New producers write ordinary files in the final tree. These aliases are only a
reader compatibility boundary; there is no post-run packing or unpacking.
"""
from pathlib import Path

from .legacy_archive import _safe, archive_manifest, ArtifactFile


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
    archived = archive_manifest(root)
    if archived:
        from .legacy_archive import artifact_file as archived_file
        return archived_file(root, legacy_relative(canonical))
    for name in dict.fromkeys((canonical, str(relative), legacy_relative(canonical))):
        candidate = _safe(root, name)
        if candidate.exists():
            return candidate
    raise FileNotFoundError(root / canonical)


def resolve_artifact_path(path):
    path = Path(path)
    for root in path.parents:
        if ((root / 'run.json').is_file() or (root / 'evaluation/manifest.json').is_file()
                or (root.parent.name == 'trajectory' and archive_manifest(root))):
            return artifact_file(root, path.relative_to(root).as_posix())
    return path
