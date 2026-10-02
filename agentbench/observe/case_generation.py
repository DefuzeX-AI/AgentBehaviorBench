"""Expose saved Case preparation evidence without loading or calling an SDK."""
import json
import re
from .result_files import read_json


def generation(directory):
    metadata = read_json(directory, 'run.json') or {}
    collection = read_json(directory, 'evaluation/case-collection.json') or {}
    cases = []
    for position, entry in enumerate(collection.get('cases', [])):
        if not isinstance(entry, dict):
            continue
        reference = entry.get('artifact', '')
        # Public exports mirror the private SDK ledger, but never browse that ledger.
        match = re.fullmatch(r'\.kuma/([^/\\:]+\.json)', reference) if isinstance(reference, str) else None
        payload = read_json(directory, f'evaluation/cases/{match[1]}') if match else None
        cases.append({'entry': {**entry, 'case_index': entry.get('case_index', position)},
                      'artifact': payload})
    return {'run_id': metadata.get('run_id'), 'metadata': metadata,
            'collection': collection, 'cases': cases,
            'profile': read_json(directory, 'evaluation/case-generation-profile.json'),
            'request': read_json(directory, 'request/evaluation.json'),
            'selection': read_json(directory, 'evaluation/batch-selection.json'),
            'error': read_json(directory, 'evaluation/error.json')}


if __name__ == '__main__':
    import sys
    print(json.dumps(generation(sys.argv[1]), ensure_ascii=True))
