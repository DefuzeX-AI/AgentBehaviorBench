"""Prepare all Cases before execution, using the SDK's file-based Case artifacts.

The SDK has no batch entry point: a Case is created by ``create_run`` and becomes
reusable only through ``Run.save_case`` / ``create_run(case_path=...)``. Preparation
therefore creates one Run per requested Case, saves that Case as a
``kuma.case_artifact.v1`` file inside the Run repository, and cancels the Run without
executing the Agent. Execution later reuses those files.
"""
import json
from pathlib import Path, PurePosixPath

from agentbench.sdk.common.case_identity import case_content_sha256
from .compatibility import artifact_case
from .generation_failures import blocks_generation, failure_record

SCHEMA = 'abb.case_collection.v2'
LEDGER = '.kuma'


def selected_indices(count, case_indices=None):
    """Validate zero-based original slots; subsets never change slot identity."""
    if type(count) is not int or count < 1:
        raise ValueError('Case count must be a positive integer')
    indices = tuple(range(count)) if case_indices is None else tuple(case_indices)
    if any(type(index) is not int or not 0 <= index < count for index in indices):
        raise ValueError('Case indices must be integers within the registered count')
    if len(indices) != len(set(indices)):
        raise ValueError('Case indices must be distinct')
    return tuple(sorted(indices))


def generate_collection(create_run, *, count, options, files, repo,
                        case_indices=None, allow_partial=False, case_options=None):
    """Save each requested slot once, preserving successes across later failures.

    ``count`` is the total registered count, while ``case_indices`` selects the
    original slots to generate. In partial mode a failed slot is recorded and
    ordinary errors allow other slots to proceed; no failed request is retried.
    Legacy callers retain exception propagation and complete-count validation.
    ``case_options`` optionally maps a slot index to extra ``create_run`` options,
    for a Case provider whose content depends on the slot: slots must not repeat
    content, and the SDK gives a provider no slot of its own.
    """
    indices = selected_indices(count, case_indices)
    repo = Path(repo)
    collection = {'schema': SCHEMA, 'requested_count': count, 'cases': [],
                  'selected_case_indices': list(indices), 'failures': [],
                  'unattempted_indices': list(indices)}
    files.save('case-collection.json', collection)
    for index in indices:
        collection['active_case_index'] = index
        files.save('case-collection.json', collection)
        try:
            slot_options = options if case_options is None else {**options, **case_options(index)}
            entry = _generate_case(create_run, slot_options, files, index)
            validate_entries([*collection['cases'], entry], count=count)
            collection['cases'].append(entry)
        except Exception as exc:
            collection.pop('active_case_index', None)
            collection['failures'].append(failure_record(exc, index, repo=repo))
            collection['unattempted_indices'].remove(index)
            files.save('case-collection.json', collection)
            if not allow_partial:
                raise
            if blocks_generation(exc):
                break
        else:
            collection.pop('active_case_index', None)
            collection['unattempted_indices'].remove(index)
        files.save('case-collection.json', collection)
        files.save('manifest.json', {'phase': 'case_generation', 'requested_count': count,
                                     'generated_count': len(collection['cases']),
                                     'failed_count': len(collection['failures'])})
    if not allow_partial and len(collection['cases']) != len(indices):
        raise ValueError('SDK returned an unexpected Case count')
    return collection


def _generate_case(create_run, options, files, index):
    relative = f'{LEDGER}/abb-case-{index + 1:04d}.json'
    run = create_run(**options)
    primary_error = None
    try:
        saved = run.save_case(relative)
        artifact = json.loads(Path(saved).read_text(encoding='utf-8'))
        case = artifact_case(artifact)
        if case['case_id'] != run.case_id:
            raise ValueError('Saved Case identity does not match the generated Run')
        # Export through the worker's output mount; the SDK ledger is private to
        # its container user and cannot serve as the host's reusable file.
        files.save(f'cases/{Path(relative).name}', artifact)
        return {'case_index': index, 'case_id': run.case_id, 'artifact': relative,
                'origin': artifact.get('origin'), 'content_sha256': case_content_sha256(case)}
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        try:
            run.cancel()
        except Exception:
            if primary_error is None:
                raise


def validate_collection(collection, *, count):
    """Validate complete selection and content before any execution container starts."""
    if not isinstance(collection, dict):
        raise ValueError('Case collection must be an object')
    if collection.get('schema') != SCHEMA:
        raise ValueError('Unsupported Case collection schema')
    if collection.get('requested_count') != count:
        raise ValueError('Case collection requested count does not match this evaluation')
    cases = collection.get('cases')
    if not isinstance(cases, list) or len(cases) != count:
        raise ValueError(f'SDK returned an unexpected Case count; requested {count}')
    validate_entries(cases, count=count)
    indices = {entry.get('case_index', index) for index, entry in enumerate(cases)}
    if indices != set(range(count)):
        raise ValueError('Complete collection must contain every original Case slot')
    return collection


def validate_entries(cases, *, count):
    """Check selection metadata without weakening complete-collection imports."""
    seen, identifiers, artifacts = set(), set(), set()
    indices = set()
    for position, entry in enumerate(cases):
        if not isinstance(entry, dict):
            raise ValueError('Invalid Case collection entry')
        index = entry.get('case_index', position)
        selected_indices(count, (index,))
        if index in indices:
            raise ValueError('Case collection contains duplicate Case indices')
        indices.add(index)
        case_id, artifact = entry.get('case_id'), entry.get('artifact')
        fingerprint = entry.get('content_sha256')
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError('Invalid Case identifier')
        if not isinstance(artifact, str):
            raise ValueError('Invalid Case artifact reference')
        path = PurePosixPath(artifact)
        if (len(path.parts) != 2 or path.parts[0] != LEDGER or path.parts[1] in ('.', '..')
                or path.as_posix() != artifact or '\\' in artifact):
            raise ValueError('Invalid Case artifact reference')
        if (not isinstance(fingerprint, str) or len(fingerprint) != 64
                or any(character not in '0123456789abcdef' for character in fingerprint)):
            raise ValueError('Invalid Case content fingerprint')
        if fingerprint in seen or case_id in identifiers or artifact in artifacts:
            raise ValueError('SDK returned duplicate Case content or IDs; no Agent steps were executed')
        seen.add(fingerprint)
        identifiers.add(case_id)
        artifacts.add(artifact)
    return cases
