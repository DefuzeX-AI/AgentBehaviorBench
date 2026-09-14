"""Protect persisted Suite and Attempt paths from default-history cleanup."""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path

from .atomic import atomic_json
from .locking import SuiteLock, SuiteLockedError
from .plan import PLAN_SCHEMA
from .store import read_suite

INDEX_SCHEMA = 'abb.suite.reference.v1'


@dataclass(frozen=True, slots=True)
class SuiteReferences:
    suite_id: str
    directory: Path
    paths: tuple[Path, ...]


def _cache(project_root, *, create=False):
    path = Path(project_root).resolve() / 'cache'
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise ValueError('Suite reference cache must be a real directory')
    if create:
        path.mkdir(exist_ok=True)
    return path


@contextmanager
def history_guard(project_root):
    """Serialize fresh Suite publication against history moves, across processes.

    Hold this only while creating/indexing a Suite or checking/moving cleanup
    targets. A running Suite's protected references need no long-lived lock.
    """
    directory = _cache(project_root, create=True) / 'history-guard'
    if directory.is_symlink() or (directory / '.writer.lock').is_symlink():
        raise ValueError('History coordination lock must not be a symlink')
    lock = SuiteLock(directory)
    try:
        lock.acquire()
    except SuiteLockedError as exc:
        raise RuntimeError('History cleanup or Suite creation is already in progress; try again') from exc
    try:
        yield
    finally:
        lock.close()


def register_suite_reference(directory, *, project_root):
    """Index a validated Suite, including one stored outside default results.

    Fresh creation must hold ``history_guard`` around SuiteStore.begin and this
    call, before dispatching work. Each Suite owns a separate atomic index file.
    Only its path and identity are recorded; no environment or credentials.
    """
    directory = Path(directory).resolve()
    plan, _ = read_suite(directory)
    index = _cache(project_root, create=True) / 'suite-references'
    if index.is_symlink():
        raise ValueError('Suite reference index must not be a symlink')
    index.mkdir(exist_ok=True)
    key = hashlib.sha256(str(directory).encode()).hexdigest()
    atomic_json(index / f'{key}.json', {
        'schema': INDEX_SCHEMA, 'suite_id': plan['suite_id'], 'directory': str(directory)})


def collect_suite_references(project_root):
    """Read every discoverable/indexed Suite, retaining all historical Attempts.

    Old standalone result imports without a durable Suite plan are not promoted
    into recoverable Suites. Malformed indexed/durable state fails closed.
    """
    root = Path(project_root).resolve()
    candidates = set(_discover_suites(root / 'results'))
    indexed = {}
    index = _cache(root) / 'suite-references'
    if index.is_symlink():
        raise ValueError('Suite reference index must not be a symlink')
    if index.exists():
        for path in sorted(index.glob('*.json')):
            if path.is_symlink():
                raise ValueError('Suite reference entry must not be a symlink')
            value = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(value, dict) or value.get('schema') != INDEX_SCHEMA:
                raise ValueError('Invalid Suite reference index; history was not moved')
            directory = _absolute_path(value.get('directory'))
            indexed[directory] = value.get('suite_id')
            candidates.add(directory)
    references = []
    for directory in sorted(candidates):
        if directory.is_symlink() or (directory / 'plan.json').is_symlink() or (directory / 'events.json').is_symlink():
            raise ValueError('Linked Suite state cannot be safely checked for cleanup')
        try:
            plan, events = read_suite(directory)
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            raise ValueError(f'Cannot verify saved Suite references at {directory}; history was not moved') from exc
        if directory in indexed and indexed[directory] != plan['suite_id']:
            raise ValueError('Suite reference identity changed; history was not moved')
        paths = {directory}
        try:
            for event in events:
                paths.update(_event_paths(event))
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise ValueError(f'Cannot verify artifact references for Suite {plan["suite_id"]}; history was not moved') from exc
        references.append(SuiteReferences(plan['suite_id'], directory, tuple(sorted(paths))))
    return tuple(references)


def _discover_suites(results):
    if not results.is_dir():
        return
    for directory, folders, files in os.walk(results, followlinks=False):
        path = Path(directory)
        folders[:] = [name for name in folders if not (path / name).is_symlink()]
        if 'plan.json' not in files:
            continue
        candidate = path / 'plan.json'
        recognizable = path.parent.name == 'suites' or path.name.startswith('suite_')
        try:
            value = json.loads(candidate.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            if recognizable:
                yield path
            continue
        if recognizable or isinstance(value, dict) and value.get('schema') == PLAN_SCHEMA:
            yield path
            folders[:] = []  # Case files within this Suite are protected with it.


def _absolute_path(value):
    if not isinstance(value, str) or not value or not Path(value).is_absolute():
        raise ValueError('Saved Suite artifact references must be absolute paths')
    return Path(value).resolve()


def _event_paths(event):
    """Read host-owned reference fields; never scan Agent prompt/output content."""
    for key in ('artifact_directory',):
        if event.get(key) is not None:
            yield _absolute_path(event[key])
    prepared = event.get('prepared_case') or {}
    if prepared.get('artifact_path') is not None:
        yield _absolute_path(prepared['artifact_path'])
    if isinstance(event.get('case_result'), dict):
        yield from _result_paths(event['case_result'])
    item = event.get('item') or {}
    for result in item.get('case_results', ()):
        yield from _result_paths(result)
    failure = item.get('preparation_error') or {}
    yield from _artifact_paths(failure.get('artifacts'))


def _result_paths(result):
    yield from _artifact_paths(result.get('artifacts'))
    benchmark = result.get('benchmark') or {}
    report = benchmark.get('report') or {}
    directory = (report.get('extensions') or {}).get('abb_artifact_directory')
    if directory is not None:
        yield _absolute_path(directory)


def _artifact_paths(artifacts):
    if artifacts is not None and not isinstance(artifacts, dict):
        raise ValueError('Saved Attempt artifacts must be an object')
    if artifacts is not None and artifacts.get('directory') is not None:
        yield _absolute_path(artifacts['directory'])
