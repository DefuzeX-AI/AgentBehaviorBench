"""Allocate persistent artifact roots before any SDK work starts."""
from pathlib import Path
from uuid import uuid4


def allocate_run(output, store, agent_id, identity, indices=None):
    identity = dict(identity or {})
    if store is None:
        parent = Path(output).resolve()
        parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        parent.chmod(0o700)
        return parent / uuid4().hex
    if indices is not None:
        for index in indices:
            store.case(agent_id, index)
        # A generation job may fill several slots. Its original diagnostics
        # remain together; each successful Case is published independently.
        if hasattr(store, 'preparation'):
            return store.preparation(agent_id)
        path = store.directory / 'preparation' / uuid4().hex
        path.mkdir(parents=True, mode=0o700)
        return path
    case = store.case(agent_id, identity['case_index'])
    attempt_id = identity.get('attempt_id')
    if not attempt_id:
        # Without a scheduler attempt number, redraw a short ID that is already taken.
        for _ in range(100):
            attempt_id = uuid4().hex[:8]
            if not (Path(case.directory) / 'attempts' / attempt_id).exists():
                break
        else:
            raise RuntimeError('No unused attempt ID after 100 attempts')
    return case.attempt(attempt_id).directory
