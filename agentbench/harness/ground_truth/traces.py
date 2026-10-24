"""Saved trace normalization shared by GT migration and comparison."""
import json
from pathlib import Path
from .files import read_bytes, within


def read_trace(api, *, limit=8 * 1024 * 1024):
    events, warnings, size = [], [], 0

    def read(relative):
        nonlocal size
        path = api.file(relative)
        from agentbench.observe.artifact_paths import ArtifactFile
        raw = path.read_bytes() if isinstance(path, ArtifactFile) else read_bytes(path, limit=limit)
        size += len(raw)
        if size > limit:
            raise ValueError('Trace exceeds context limit; no silent truncation')
        return json.loads(raw)

    for folder in api.outputs():
        for name in ('input.json', 'result.json'):
            try:
                value = read(f'{folder}/{name}')
                events.append({'id': f'{folder}/{name}', 'kind': name[:-5], 'content': value})
            except FileNotFoundError:
                warnings.append(f'Missing {folder}/{name}')
    spans = api.spans()
    warnings.extend(spans.get('warnings', []))
    for span in spans['spans']:
        attrs = span.get('attributes') or {}
        kind = attrs.get('abb.kind')
        if kind not in ('tool', 'llm', 'model', 'chat') and 'ArtifactCapture' not in span.get('name', ''):
            continue
        folder = span['output_directory']
        event = {'id': f"{folder}/{span['span_id']}", 'kind': kind,
                 'name': span.get('name'), 'status': span.get('status'),
                 'start_time': span.get('start_time')}
        for field in ('input', 'output', 'error'):
            ref = attrs.get(f'abb.{field}_ref')
            if not ref:
                continue
            # Runtime references are relative to the input capture directory.
            try:
                event[field] = read(f'{folder}/{ref}')
            except FileNotFoundError as exc:
                warnings.append(f'{event["id"]}: unavailable {field} payload ({type(exc).__name__})')
        if any(k in event for k in ('input', 'output', 'error')):
            events.append(event)
    if not events:
        raise ValueError('No captured trace events')
    return {'events': events, 'warnings': warnings, 'capture_statuses': spans.get('statuses', [])}


def read_reference_traces(defect, *, limit=8 * 1024 * 1024):
    """Normalize original retained case attempts in memory, never flatten on disk."""
    from agentbench.observe.view_api import RunViewAPI
    root = Path(defect['_case_directory'])
    traces = []
    for attempt in defect['reference_attempts']:
        parent = 'trajectory' if (root / 'trajectory').is_dir() else 'attempts'
        directory = within(root, root / parent / attempt)
        trace = read_trace(RunViewAPI(directory), limit=limit)
        for event in trace['events']:
            event['id'] = attempt + '/' + event['id']
        traces.append({'id': attempt, 'kind': 'agent', **trace})
    return traces
