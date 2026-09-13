"""Prepare all Cases before execution, using the SDK's file-based Case artifacts.

The SDK has no batch entry point: a Case is created by ``create_run`` and becomes
reusable only through ``Run.save_case`` / ``create_run(case_path=...)``. Preparation
therefore creates one Run per requested Case, saves that Case as a
``kuma.case_artifact.v1`` file inside the Run repository, and cancels the Run without
executing the Agent. Execution later reuses those files.
"""
import json
from pathlib import Path

from agentbench.sdk.common.case_identity import case_content_sha256

SCHEMA = 'abb.case_collection.v2'
LEDGER = '.kuma'


def artifact_case(artifact):
    """Return the normalized Case mapping inside a validated Case artifact.

    An official artifact stores the original signed wire content, whose steps are not
    the normalized inputs; the SDK's own converter is the only correct way to read it.
    """
    from kuma.repository.case_artifacts import artifact_case_mapping

    if not isinstance(artifact, dict) or artifact.get('schema_version') is None:
        raise ValueError('Invalid Case artifact')
    if not isinstance(artifact.get('case'), dict):
        raise ValueError('Case artifact carries no Case content')
    return artifact_case_mapping(artifact)


def generate_collection(create_run, *, count, options, files, repo):
    """Create and save `count` distinct Cases without invoking the Agent."""
    if type(count) is not int or count < 1:
        raise ValueError('Case count must be a positive integer')
    repo = Path(repo)
    collection = {'schema': SCHEMA, 'requested_count': count, 'cases': []}
    for index in range(count):
        relative = f'{LEDGER}/abb-case-{index + 1:04d}.json'
        run = create_run(**options)
        try:
            saved = run.save_case(relative)
        finally:
            # Preparation never executes the Agent; release the Run either way.
            run.cancel()
        artifact = json.loads(Path(saved).read_text(encoding='utf-8'))
        # The SDK publishes the artifact with restrictive permissions inside the Run
        # repository, which the host cannot read. Export a copy through this container's
        # own output channel so preparation results survive the container.
        files.save(f'cases/{Path(relative).name}', artifact)
        case = artifact_case(artifact)
        collection['cases'].append({
            'case_id': run.case_id, 'artifact': relative, 'origin': artifact.get('origin'),
            'content_sha256': case_content_sha256(case)})
        files.save('case-collection.json', collection)
        files.save('manifest.json', {'phase': 'case_generation', 'requested_count': count,
                                     'generated_count': len(collection['cases'])})
    if len(collection['cases']) != count:
        raise ValueError('SDK returned an unexpected Case count')
    return collection


def validate_collection(collection, *, count):
    """Validate complete selection and content before any execution container starts."""
    if not isinstance(collection, dict):
        raise ValueError('Case collection must be an object')
    if collection.get('schema', SCHEMA) != SCHEMA:
        raise ValueError('Unsupported Case collection schema')
    if collection.get('requested_count', count) != count:
        raise ValueError('Case collection requested count does not match this evaluation')
    cases = collection.get('cases')
    if not isinstance(cases, list) or len(cases) != count:
        raise ValueError(f'SDK returned an unexpected Case count; requested {count}')
    seen, identifiers = set(), set()
    for entry in cases:
        if not isinstance(entry, dict):
            raise ValueError('Invalid Case collection entry')
        case_id, artifact = entry.get('case_id'), entry.get('artifact')
        fingerprint = entry.get('content_sha256')
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError('Invalid Case identifier')
        if not isinstance(artifact, str) or not artifact.startswith(f'{LEDGER}/'):
            raise ValueError('Invalid Case artifact reference')
        if not isinstance(fingerprint, str) or len(fingerprint) != 64:
            raise ValueError('Invalid Case content fingerprint')
        if fingerprint in seen or case_id in identifiers:
            raise ValueError('SDK returned duplicate Case content or IDs; no Agent steps were executed')
        seen.add(fingerprint)
        identifiers.add(case_id)
    return collection
