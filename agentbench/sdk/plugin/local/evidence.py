"""Lossless JSONL presentation for the local Judge; original attachments stay intact.

Stream events repeat large context envelopes. Factor fields shared by adjacent
records, not their content, order, timestamps or tool results. No Agent-specific
filter or verdict-dependent selection is applied.
"""
import json
from itertools import groupby


def _object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('Duplicate JSON key')
        value[key] = item
    return value


def _invalid_constant(value):
    raise ValueError('Non-finite JSON constant')


def _records(text):
    return [json.loads(line, object_pairs_hook=_object, parse_constant=_invalid_constant)
            for line in text.splitlines() if line.strip()]


def _common(records):
    if len(records) < 2 or not all(isinstance(row, dict) for row in records):
        return {}
    shared = {}
    for key, value in records[0].items():
        if not all(key in row and type(row[key]) is type(value) for row in records):
            continue
        values = [row[key] for row in records]
        if isinstance(value, dict):
            nested = _common(values)
            if nested or all(item == {} for item in values):
                shared[key] = nested
        elif all(item == value for item in values):
            shared[key] = value
    return shared


def _subtract(record, shared):
    if not isinstance(record, dict):
        return record
    result = {}
    for key, value in record.items():
        if key not in shared:
            result[key] = value
        elif isinstance(value, dict):
            remainder = _subtract(value, shared[key])
            if remainder:
                result[key] = remainder
    return result


def _merge(shared, record):
    if not isinstance(record, dict):
        return record
    merged = dict(shared)
    for key, value in record.items():
        merged[key] = (_merge(shared[key], value)
                       if key in shared and isinstance(shared[key], dict) and isinstance(value, dict)
                       else value)
    return merged


def restore_trace(value):
    """Reconstruct every original JSON record for independent evidence audits."""
    if isinstance(value, str):
        return _records(value)
    return [_merge(block['common_fields'], row)
            for block in value['blocks'] for row in block['records']]


def project_trace(text):
    """Use a structured view only when it is lossless and smaller than raw JSONL."""
    try:
        records = _records(text)
    except (ValueError, TypeError):
        return text
    blocks = []
    def event_kind(row):
        if not isinstance(row, dict):
            return None
        data = row.get('data')
        return row.get('event'), data.get('name') if isinstance(data, dict) else None
    for _, group in groupby(records, key=event_kind):
        rows = list(group)
        shared = _common(rows)
        blocks.append({'common_fields': shared,
                       'records': [_subtract(row, shared) for row in rows]})
    value = {'format': 'abb.judge.jsonl.v1',
             'inheritance': 'Every record recursively inherits its block common_fields. Blocks and records retain source order.',
             'blocks': blocks}
    # Keep the raw presentation if the round-trip cannot preserve the JSON data.
    canonical = lambda data: json.dumps(data, ensure_ascii=False, sort_keys=True)
    if canonical(restore_trace(value)) != canonical(records):
        return text
    return value if len(json.dumps(value, ensure_ascii=False)) < len(json.dumps(text, ensure_ascii=False)) else text
