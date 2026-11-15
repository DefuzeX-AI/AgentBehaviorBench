"""Resolve recorded inputs across benchmark and standalone invocation layouts.

Paths remain relative to the run and are read through the guarded artifact API.
The request envelope is evidence, not a reason to manufacture a benchmark Input ID.
"""
from pathlib import PurePosixPath


def standalone_output(folder):
    parts = PurePosixPath(folder).parts
    return len(parts) == 2 and parts[0].startswith('invocation-') and parts[1] == 'output'


def request_paths(folder):
    paths = [f'{folder}/request.json', f'{folder}/invocation.json']
    if standalone_output(folder):
        paths.insert(0, str(PurePosixPath(folder).parent / 'input' / 'request.json'))
    return paths


def read_input_artifacts(folder, read):
    record = read(f'{folder}/input.json')
    request = None
    for path in request_paths(folder):
        request = read(path)
        if request is not None:
            break
    if record is not None and not isinstance(record, dict):
        raise ValueError('Recorded Input must be an object')
    if request is not None and not isinstance(request, dict):
        raise ValueError('Invocation request must be an object')
    request = request or {}
    if (record is None and standalone_output(folder)
            and request.get('schema') == 'abb.invocation.v1' and 'input' in request):
        context = request.get('observation_context') or {}
        record = {'payload': request['input'], 'input_id': context.get('input_id'),
                  'case_id': context.get('case_id')}
    return record, request


def input_ordinal(folder):
    if not folder:
        return None
    path = PurePosixPath(folder)
    return path.parent.name if standalone_output(folder) else path.name
