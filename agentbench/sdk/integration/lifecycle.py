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
    return case.attempt(identity.get('attempt_id') or uuid4().hex).directory
