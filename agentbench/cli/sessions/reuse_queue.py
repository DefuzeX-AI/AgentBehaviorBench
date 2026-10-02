"""Durable inbox consumed only by the reuse Suite's owning coordinator."""

import json

from agentbench.harness.session.admission import admit_reuse_request
from agentbench.harness.session.atomic import atomic_json


def requests(directory):
    entries = [(path, json.loads(path.read_text())) for path in
               (directory / 'reuse-requests').glob('*/request.json')]
    return sorted(entries, key=lambda entry: (entry[1].get('received_at_ns', 0), entry[1]['request_id']))


def admit_waiting(store):
    for path, request in requests(store.directory):
        if request.get('slots') is None:
            request['slots'] = admit_reuse_request(store, request)
            atomic_json(path, request)


def unfinished_slots(store):
    """Never rerun a previous terminal outcome merely because another request arrived."""
    cases = {(job['agent_id'], case['case_index']): case for job in store.snapshot()['jobs'] for case in job['cases']}
    selection = set()
    for path, request in requests(store.directory):
        slots = [tuple(slot) for slot in request.get('slots') or []]
        if request.get('status') == 'completed':
            continue
        if slots and all(cases[slot]['result'] is not None for slot in slots):
            request['status'] = 'completed'
            atomic_json(path, request)
        else:
            selection.update(slots)
    return selection
