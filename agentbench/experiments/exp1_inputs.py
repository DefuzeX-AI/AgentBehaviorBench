"""Validate and freeze an ordered, externally generated Case collection."""
from pathlib import Path

from agentbench.harness.ground_truth.files import read_json
from agentbench.sdk.plugin.native.backend import validate_case


def load_cases(path):
    path = Path(path)
    if not path.is_absolute():
        raise ValueError('--cases must be an absolute path to a JSON file')
    if not path.is_file() or path.suffix.lower() != '.json':
        raise ValueError('--cases must name an existing JSON file')
    document = read_json(path)
    if document.get('schema') != 'abb.cases.v1' or not isinstance(document.get('cases'), list):
        raise ValueError('Expected an abb.cases.v1 collection with a cases array')
    cases = document['cases']
    if not 1 <= len(cases) <= 50:
        raise ValueError('Supply between 1 and 50 Cases')
    cases = [validate_case(case) for case in cases]
    if len({case['case_id'] for case in cases}) != len(cases):
        raise ValueError('Case IDs must be unique')
    return cases
