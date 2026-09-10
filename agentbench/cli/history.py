"""Recoverable cleanup of the project's default result history only."""
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def history_targets(root=PROJECT_ROOT):
    root = root.resolve()
    results = root / 'results'
    if results.is_symlink():
        raise ValueError('Refusing to clean a symlinked results directory')
    if not results.exists():
        return ()
    if not results.is_dir():
        raise ValueError('results must be a directory')
    return tuple(sorted(results.iterdir()))


def archive_history(targets, root=PROJECT_ROOT):
    """Move immediate children, never follow symlinks or recursively delete."""
    root = root.resolve()
    if tuple(targets) != history_targets(root):
        raise ValueError('History changed after preview; run clean again')
    cache = root / 'cache'
    if cache.is_symlink():
        raise ValueError('Refusing to use a symlinked cache directory')
    cache.mkdir(exist_ok=True)
    trash = cache / 'history-trash'
    if trash.is_symlink():
        raise ValueError('Refusing to use a symlinked history archive')
    trash.mkdir(exist_ok=True)
    batch = trash / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid4().hex)
    batch.mkdir(mode=0o700)
    for target in targets:
        try:
            target.rename(batch / target.name)
        except OSError as exc:
            raise RuntimeError(f'Cleanup interrupted; already moved history is recoverable at {batch}') from exc
    return batch
