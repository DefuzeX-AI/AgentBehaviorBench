"""Freeze externally generated Cases in explicit per-Issue execution order."""
import re
from pathlib import Path

from agentbench.harness.ground_truth.files import read_json, within
from agentbench.sdk.plugin.native.backend import validate_case


def load_cases(directory, budget):
    if type(budget) is not int or not 1 <= budget <= 50:
        raise ValueError('--tests must be between 1 and 50')
    directory = Path(directory).resolve()
    if not directory.is_dir():
        raise ValueError('--case-dir must be a directory containing issue_<number> folders')
    folders = sorted(directory.iterdir(), key=lambda p: p.name)
    groups = []
    identities = set()
    for folder in folders:
        if not folder.is_dir():
            if folder.suffix == '.json':
                raise ValueError('Place Cases inside issue_<number> folders')
            continue
        if not re.fullmatch(r'issue_[1-9][0-9]*', folder.name):
            raise ValueError(f'Unexpected Case folder: {folder.name}')
        folder = within(directory, folder)
        paths = list(folder.glob('*.json'))
        collection = folder / 'cases.json'
        if collection.exists():
            if len(paths) != 1:
                raise ValueError(f'{folder.name}: use cases.json OR numbered Case files')
            value = read_json(collection)
            if not isinstance(value, dict) or value.get('schema') != 'abb.cases.v1' or not isinstance(value.get('cases'), list):
                raise ValueError(f'{folder.name}: expected an abb.cases.v1 collection')
            cases = value['cases']
        else:
            if not paths or any(not re.fullmatch(r'[0-9]+\.json', p.name) for p in paths):
                raise ValueError(f'{folder.name}: expected numbered files such as 0001.json')
            indices = [int(p.stem) for p in paths]
            if len(set(indices)) != len(indices) or min(indices) < 1:
                raise ValueError(f'{folder.name}: duplicate or invalid test numbers')
            cases = [read_json(within(folder, p)) for p in sorted(paths, key=lambda p: int(p.stem))]
        if not cases:
            raise ValueError(f'{folder.name}: no Cases supplied')
        if any(not isinstance(c, dict) for c in cases):
            raise ValueError(f'{folder.name}: each Case must be a JSON object')
        cases = [validate_case(c) for c in cases]
        ids = [c.get('case_id') for c in cases]
        if any(not isinstance(c, str) or not c.strip() for c in ids) or len(set(ids)) != len(ids):
            raise ValueError(f'{folder.name}: Case IDs must be nonempty and unique')
        number = int(folder.name.split('_')[1])
        if number in identities:
            raise ValueError('Duplicate Issue identity')
        identities.add(number)
        # Preserve array order or numeric filename order, never completion order.
        groups.append({'issue_id': folder.name, 'issue_number': number,
                       'available_cases': len(cases), 'cases': cases[:budget]})
    if not groups:
        raise ValueError('No issue_<number> Case folders found')
    return groups
