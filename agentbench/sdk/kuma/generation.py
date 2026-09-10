"""Prepare all Cases before execution, retaining each original signed batch."""


def generate_collection(generate, *, count, options, files):
    if type(count) is not int or count < 1:
        raise ValueError('Case count must be a positive integer')
    collection = {'schema': 'abb.case_collection.v1', 'requested_count': count,
                  'mode': 'batch', 'batches': [], 'entries': []}

    def append(batch):
        index = len(collection['batches'])
        collection['batches'].append(batch)
        collection['entries'].extend({'batch_index': index, 'case_index': i}
                                     for i in range(len(batch['cases'])))
        files.save('case-collection.json', collection)
        files.save('manifest.json', {'phase': 'case_generation', 'mode': collection['mode'],
                                    'requested_count': count, 'generated_count': len(collection['entries'])})

    try:
        batch = generate(count=count, **options)
    except Exception as exc:
        if count == 1 or getattr(exc, 'code', None) != 'case_batch_unsupported':
            raise
        collection.update(mode='single_fallback', fallback_reason=exc.code)
        files.save('case-collection.json', collection)
        for _ in range(count):
            append(generate(count=1, **options))
    else:
        append(batch)
    if len(collection['entries']) != count:
        raise ValueError('SDK returned an unexpected Case count')
    return collection


def validate_collection(collection, *, count):
    """Validate complete selection and content before any execution container starts."""
    from agentbench.sdk.common.case_identity import case_content_sha256
    if not isinstance(collection, dict):
        raise ValueError('Case collection must be an object')
    if collection.get('schema', 'abb.case_collection.v1') != 'abb.case_collection.v1':
        raise ValueError('Unsupported Case collection schema')
    if collection.get('requested_count', count) != count:
        raise ValueError('Case collection requested count does not match this evaluation')
    entries, batches = collection.get('entries'), collection.get('batches')
    if not isinstance(entries, list) or len(entries) != count or not isinstance(batches, list):
        raise ValueError(f'SDK returned an unexpected Case count; requested {count}')
    seen, identifiers = set(), set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError('Invalid Case collection entry')
        batch_index, case_index = entry.get('batch_index'), entry.get('case_index')
        if type(batch_index) is not int or not 0 <= batch_index < len(batches):
            raise ValueError('Invalid Case collection batch index')
        batch = batches[batch_index]
        cases = batch.get('cases') if isinstance(batch, dict) else None
        if not isinstance(cases, list) or type(case_index) is not int or not 0 <= case_index < len(cases):
            raise ValueError('Invalid Case collection case index')
        case = cases[case_index]
        if not isinstance(case, dict) or not isinstance(case.get('case_id'), str) or not case['case_id'].strip():
            raise ValueError('Invalid Case identifier')
        steps = case.get('steps')
        if not isinstance(steps, list) or not steps or any(
            not isinstance(step, dict) or not isinstance(step.get('prompt'), str) or not step['prompt'].strip()
            for step in steps
        ):
            raise ValueError('Invalid Case steps')
        fingerprint = case_content_sha256({'inputs': [
            {'payload_type': 'text', 'payload': step['prompt']} for step in steps]})
        if fingerprint in seen or case['case_id'] in identifiers:
            raise ValueError('SDK returned duplicate Case content or IDs; no Agent steps were executed')
        seen.add(fingerprint)
        identifiers.add(case['case_id'])
