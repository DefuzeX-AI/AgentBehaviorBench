"""Project verified execution artifacts into a bounded, traceable Judge view."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from agentbench.observe.interactions import InteractionIndex
from agentbench.observe.artifact_paths import canonical_relative, artifact_file


MAX_EVENT_CHARS = 12000
TOOL_UPDATES = frozenset({'tool_call', 'tool_call_update'})
STREAM_UPDATES = frozenset({'agent_message_chunk', 'agent_thought_chunk',
                            'usage_update', 'session_info_update'})


def _reference(relative: str, *, line: int | None = None, raw: str | None = None,
               attachments: dict) -> dict:
    reference = {'path': relative, 'sha256': attachments[relative]['sha256']}
    if line is not None:
        reference['line'] = line
        reference['line_sha256'] = hashlib.sha256(raw.encode('utf-8')).hexdigest()
    return reference


def _selected(record: dict) -> tuple[str, object] | None:
    kind = record.get('event')
    data = record.get('data')
    if not isinstance(data, dict):
        return None
    if kind != 'native_event':
        return str(kind), data
    name = data.get('name')
    payload = data.get('payload')
    if not isinstance(name, str) or not isinstance(payload, dict):
        return 'native_event', data
    update = payload.get('update')
    if name.endswith('.session_update') and isinstance(update, dict):
        if update.get('sessionUpdate') in TOOL_UPDATES:
            return update['sessionUpdate'], update
        if update.get('sessionUpdate') in STREAM_UPDATES:
            return None
    return name, payload


def _excluded_kind(record: dict) -> str:
    kind = str(record.get('event', 'unknown'))
    if kind != 'native_event':
        return kind
    data = record.get('data')
    if not isinstance(data, dict):
        return kind
    name = str(data.get('name') or kind)
    payload = data.get('payload')
    update = payload.get('update') if isinstance(payload, dict) else None
    if isinstance(update, dict) and isinstance(update.get('sessionUpdate'), str):
        return name + '.' + update['sessionUpdate']
    return name


def _verified_index(request, directory):
    """Use the shared reader, restricted to this request's verified attachments."""
    files = []
    for name, metadata in request['attachments'].items():
        if name.endswith(('/framework.jsonl', '/spans.jsonl', '/input.json', '/result.json', '/request.json')):
            files.append((name, metadata.get('size_bytes', 0), 0))
    return InteractionIndex(directory, files)


def _records(index, relative, attachments):
    if relative not in attachments:
        return
    # The shared index already decoded these records. Read original bytes only
    # for line hashes; do not independently parse or group the trace again.
    lines = artifact_file(index.root, relative).read_text(encoding='utf-8').splitlines(keepends=True)
    records = [record for group in index.groups.values() for record in group
               if record['file'] == relative and record['line'] is not None]
    for record in sorted(records, key=lambda r: r['line']):
        yield record['line'], lines[record['line'] - 1], record['raw']


def _tool_reference(index, prefix, call_id):
    """Join supplemental records only to a unique indexed execution in this Input."""
    if not call_id:
        return None
    candidates = [row for row in index.rows if row['kind'] == 'tool'
                  and row.get('tool_call_id') == call_id
                  and canonical_relative(row.get('_context') or '') == canonical_relative(prefix)]
    return {'tool_call_id': call_id,
            'status': 'exact' if len(candidates) == 1 else 'ambiguous' if candidates else 'unobserved',
            'interaction_ids': [row['id'] for row in candidates]}


def _time(value: object) -> datetime:
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.max.replace(tzinfo=timezone.utc)


def project(request: dict, directory: Path) -> tuple[dict, list[str]]:
    """Return a model-facing timeline and any information lost by the projection.

    The caller validates all attachment hashes before calling this function. Raw
    files stay in place. Every projected event names its original file and line.
    Unselected streaming chunks are counted, while final Agent output is included
    from result.json. Any oversized selected event blocks a model verdict.
    """
    directory = Path(directory).resolve()
    attachments = request['attachments']
    index = _verified_index(request, directory)
    steps = []
    gaps = list(index.warnings)
    for step in request['steps']:
        prefix = step['evidence_prefix']
        input_path, result_path = prefix + '/input.json', prefix + '/result.json'
        events = []
        skipped = Counter()
        framework = prefix + '/framework.jsonl'
        for number, raw, record in _records(index, framework, attachments):
            selection = _selected(record)
            if selection is None:
                skipped[_excluded_kind(record)] += 1
                continue
            kind, data = selection
            source = _reference(framework, line=number, raw=raw, attachments=attachments)
            item = {'kind': kind, 'time': record.get('timestamp'), 'source': source}
            if len(json.dumps(data, ensure_ascii=False)) > MAX_EVENT_CHARS:
                gaps.append(f'Oversized {kind} event at {framework}:{number}; inspect the full attachment.')
                item['detail_omitted'] = True
            else:
                item['detail'] = data
            call_id = data.get('tool_call_id') or data.get('toolCallId')
            relation = _tool_reference(index, prefix, call_id)
            if relation:
                item['tool_execution'] = relation
            events.append(item)

        # Span records can carry tool outcomes absent from framework events.
        spans = prefix + '/spans.jsonl'
        for number, raw, record in _records(index, spans, attachments):
            attributes = record.get('attributes', {})
            if not isinstance(attributes, dict) or not any(key.startswith('gen_ai.tool.') for key in attributes):
                continue
            source = _reference(spans, line=number, raw=raw, attachments=attachments)
            detail = {'name': record.get('name'), 'status': record.get('status'),
                      'attributes': {key: value for key, value in attributes.items()
                                     if key.startswith('gen_ai.tool.')}}
            item = {'kind': 'tool_span', 'time': record.get('end_time'), 'source': source}
            if len(json.dumps(detail, ensure_ascii=False)) > MAX_EVENT_CHARS:
                gaps.append(f'Oversized tool span at {spans}:{number}; inspect the full attachment.')
                item['detail_omitted'] = True
            else:
                item['detail'] = detail
            relation = _tool_reference(index, prefix, attributes.get('gen_ai.tool.call.id'))
            if relation:
                item['tool_execution'] = relation
            events.append(item)

        # Framework events and final spans can arrive in different files; their
        # recorded timestamps provide display order only, never identity or pairing.
        # Records sharing a tool_execution reference describe the same execution.
        events.sort(key=lambda event: _time(event['time']))
        file_evidence = prefix + '/file-evidence.json'
        if file_evidence in attachments:
            content = artifact_file(directory, file_evidence).read_text(encoding='utf-8')
            item = {'source': _reference(file_evidence, attachments=attachments)}
            if len(content) > MAX_EVENT_CHARS:
                gaps.append(f'Oversized file evidence at {file_evidence}; inspect the full attachment.')
                item['detail_omitted'] = True
            else:
                item['detail'] = json.loads(content)
            events.append({'kind': 'file_evidence', 'time': None, **item})
        steps.append({
            'input_id': step['input']['input_id'],
            'input': step['input']['payload'],
            'input_source': _reference(input_path, attachments=attachments),
            'output': step['result'].get('output'),
            'execution_status': step['result']['status'],
            'output_source': _reference(result_path, attachments=attachments),
            'events': events,
            'excluded_framework_events': dict(sorted(skipped.items())),
        })
    return {'schema': 'abb.local_judge.evidence.v1',
            'agent_context': request['case'].get('abb_agent_context'),
            'workspace': request.get('workspace'),
            'steps': steps}, gaps
