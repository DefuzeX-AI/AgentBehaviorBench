"""File-change evidence per SDK Input: committed diffs first, replay deltas second."""
import json


def _change_type(before, after):
    if before is None and after is not None:
        return 'created'
    if before is not None and after is None:
        return 'deleted'
    return 'modified'


def file_changes(api, folder, replay_events):
    """Return (changes, coverage) for one input folder."""
    evidence = api.read(f'{folder}/file-evidence.json') or {}
    captured = evidence.get('file_evidence') if isinstance(evidence, dict) else None
    status = ((evidence.get('capture_status') or {}).get('file_diff') or {}).get('status') if isinstance(evidence, dict) else None
    changes = []
    if isinstance(captured, dict):
        for change in captured.get('changes') or []:
            if not isinstance(change, dict):
                continue
            changes.append({'path': change.get('path'), 'old_path': change.get('old_path'),
                            'change_type': change.get('change_type'), 'diff': change.get('diff'),
                            'before_sha256': change.get('before_hash'), 'after_sha256': change.get('after_hash'),
                            'complete': change.get('complete'), 'source': 'file-evidence'})
    if changes:
        return changes, 'diff'
    input_id = (api.read(f'{folder}/input.json') or {}).get('input_id')
    for event in replay_events:
        if event.get('input_id') != input_id or not event.get('changes'):
            continue
        for change in event['changes']:
            before, after = change.get('before'), change.get('after')
            changes.append({'path': change.get('path'), 'change_type': _change_type(before, after),
                            'diff': None, 'before_sha256': (before or {}).get('blob'),
                            'after_sha256': (after or {}).get('blob'), 'complete': not event.get('partial'),
                            'source': 'replay', 'sequence': event.get('sequence')})
    if changes:
        return changes, 'replay'
    return [], 'skipped' if status == 'skipped' else 'not_observed'


def replay_events(api):
    try:
        with api.file('replay/events.jsonl').open(encoding='utf-8') as stream:
            events = []
            for line in stream:
                if line.strip():
                    try:
                        events.append(json.loads(line))
                    except ValueError:
                        continue
            return events
    except FileNotFoundError:
        return []
