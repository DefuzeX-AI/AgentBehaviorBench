"""Freeze one externally generated Case group in explicit execution order."""
import re
from pathlib import Path

from agentbench.harness.ground_truth.files import read_json, within
from agentbench.sdk.plugin.native.backend import validate_case


def load_cases(directory, budget):
    if type(budget) is not int or not 1 <= budget <= 50:
        raise ValueError('--tests must be between 1 and 50')
    directory = Path(directory).resolve()
    if not directory.is_dir():
        raise ValueError('--case-dir must be a Case group directory')
    folders = sorted(p.name for p in directory.iterdir() if p.is_dir())
    if folders:
        # Issues come from ground truth, so a Case group holds Case files only.
        raise ValueError(f'Unexpected folder in Case group: {folders[0]}')
    paths = list(directory.glob('*.json'))
    collection = directory / 'cases.json'
    if collection.exists():
        if len(paths) != 1:
            raise ValueError('Use cases.json OR numbered Case files')
        value = read_json(collection)
        if not isinstance(value, dict) or value.get('schema') != 'abb.cases.v1' or not isinstance(value.get('cases'), list):
            raise ValueError('Expected an abb.cases.v1 collection')
        cases = value['cases']
    else:
        if not paths or any(not re.fullmatch(r'[0-9]+\.json', p.name) for p in paths):
            raise ValueError('Expected numbered files such as 0001.json')
        indices = [int(p.stem) for p in paths]
        if len(set(indices)) != len(indices) or min(indices) < 1:
            raise ValueError('Duplicate or invalid test numbers')
        cases = [read_json(within(directory, p)) for p in sorted(paths, key=lambda p: int(p.stem))]
    if not cases:
        raise ValueError('No Cases supplied')
    if any(not isinstance(c, dict) for c in cases):
        raise ValueError('Each Case must be a JSON object')
    cases = [validate_case(c) for c in cases]
    ids = [c.get('case_id') for c in cases]
    if any(not isinstance(c, str) or not c.strip() for c in ids) or len(set(ids)) != len(ids):
        raise ValueError('Case IDs must be nonempty and unique')
    # Preserve array order or numeric filename order, never completion order.
    return {'available_cases': len(cases), 'cases': cases}
