"""Read-only, protocol-independent interaction index shared by Python and Vite.

Group by recorded IDs, never by adjacent timestamps or Agent-specific names.
Summaries are paginated separately from full payloads and original records.
"""
from __future__ import annotations

import hashlib
import json
import threading
from collections import Counter, OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from .tool_links import link_tools
from .native_links import link_native_calls

_CACHE = OrderedDict()
_LOCK = threading.Lock()


def decoded(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            pass
    return value


def stamp(value):
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
    except (ValueError, TypeError, AttributeError):
        return None


def _id(value):
    return hashlib.sha256(value.encode()).hexdigest()[:24]


def _time_order(value):
    parsed = stamp(value)
    return float('inf') if parsed is None else parsed


def _data(record):
    value = record['raw'].get('data')
    return value if isinstance(value, dict) else {}


def _files(root):
    names = {'network.jsonl', 'evaluation/sdk.jsonl', 'evaluation/case.json',
             'evaluation/judge/report.json', 'evaluation/manifest.json',
             'evaluation/workspace-artifacts.json', 'evaluation/workspace.json'}
    for pattern in ('evaluation/inputs/[0-9][0-9][0-9][0-9]', 'invocation-*/output'):
        for folder in root.glob(pattern):
            for name in ('framework.jsonl', 'input.json', 'mapped-input.json', 'request.json',
                         'result.json', 'submission.json', 'file-evidence.json'):
                names.add(str((folder / name).relative_to(root)))
    for path in (root / 'evaluation/workspace-files').glob('*.json'):
        names.add(str(path.relative_to(root)))
    files = []
    for name in sorted(names):
        candidate = root / name
        try:
            file = candidate.resolve(strict=True)
            if not file.is_relative_to(root) or candidate.is_symlink() or not file.is_file():
                continue
            stat = file.stat()
            files.append((name, stat.st_size, stat.st_mtime_ns))
        except FileNotFoundError:
            continue
    return files


def _read(root, name):
    path = (root / name).resolve(strict=True)
    if not path.is_relative_to(root):
        raise ValueError('Artifact outside run')
    return path


def _contains_tool(value):
    if isinstance(value, dict):
        if any(value.get(k) for k in ('tool_calls', 'function_call', 'functionCall')) or value.get('type') == 'tool_use':
            return True
        return any(_contains_tool(v) for v in value.values())
    return isinstance(value, list) and any(_contains_tool(v) for v in value)


def _matches(value, target, path='$'):
    """Return verifiable value matches, not inferred causal relationships."""
    target = decoded(target)
    value = decoded(value)
    if target is None or target == '' or target == {} or target == []:
        return []
    if type(value) is type(target) and value == target:
        return [{'path': path, 'method': 'exact_value'}]
    if isinstance(value, str) and isinstance(target, str) and len(target) >= 8 and target in value:
        return [{'path': path, 'method': 'contains_full_text'}]
    if isinstance(value, dict):
        return [hit for key, item in value.items() for hit in _matches(item, target, f'{path}[{json.dumps(key)}]')]
    if isinstance(value, list):
        return [hit for i, item in enumerate(value) for hit in _matches(item, target, f'{path}[{i}]')]
    return []


class InteractionIndex:
    def __init__(self, root, files):
        self.root = root
        self.groups = {}
        self.artifacts = {}
        self.contexts = {}
        self.warnings = []
        self.rows = []
        records = []
        for name, size, mtime in files:
            if name.endswith('.jsonl'):
                with _read(root, name).open('rb') as stream:
                    line = 0
                    while raw := stream.readline():
                        line += 1
                        if not raw.strip():
                            continue
                        try:
                            row = json.loads(raw)
                            if not isinstance(row, dict):
                                raise ValueError('Expected object')
                            records.append({'file': name, 'line': line, 'raw': row})
                        except ValueError:
                            self.warnings.append(f'{name}:{line} contains incomplete or invalid JSON')
            else:
                try:
                    self.artifacts[name] = {'value': json.loads(_read(root, name).read_text(encoding='utf-8')),
                        'timestamp': datetime.fromtimestamp(mtime / 1e9, timezone.utc).isoformat()}
                except ValueError:
                    self.warnings.append(f'{name}: contains incomplete or invalid JSON')

        for name, item in self.artifacts.items():
            if name.endswith('/input.json'):
                folder = name.rsplit('/', 1)[0]
                inp = item['value']
                self.contexts[folder] = {'folder': folder,
                    'input_id': inp.get('input_id') if isinstance(inp, dict) else None,
                    'case_id': inp.get('case_id') if isinstance(inp, dict) else None,
                    **{key: self.artifacts.get(folder + '/' + filename, {}).get('value') for key, filename in {
                        'input': 'input.json', 'mapped': 'mapped-input.json', 'invocation': 'request.json',
                        'result': 'result.json', 'submission': 'submission.json'}.items()}}
        spans = {}
        artifact_events = {}
        for record in records:
            row = record['raw']; data = row.get('data') or {}
            if not isinstance(data, dict):
                data = {}
            event = row.get('event', 'unknown')
            if record['file'].endswith('framework.jsonl') and data.get('span_id'):
                spans.setdefault(data['span_id'], []).append(record)
            if row.get('source') == 'sdk' and isinstance(data.get('artifact'), str):
                artifact_events['evaluation/' + data['artifact']] = record
                continue
            if data.get('call_id'):
                key = 'network:' + str(data['call_id'])
            elif record['file'].endswith('framework.jsonl') and data.get('span_id') and event != 'native_event':
                key = 'span:' + record['file'] + ':' + str(data['span_id'])
            else:
                key = f"event:{record['file']}:{record['line']}"
            identifier = _id(key)
            self.groups.setdefault(identifier, []).append(record)

        for identifier, group in self.groups.items():
            group.sort(key=lambda r: (_time_order(r['raw'].get('timestamp')), r['file'], r['line']))
            first = group[0]; data = first['raw'].get('data') or {}
            if not isinstance(data, dict):
                data = {}
            events = [r['raw'].get('event', '') for r in group]
            req = next((r for r in group if r['raw'].get('event') in ('llm_request', 'tool_request', 'span_start', 'execution_start')), None)
            res = next((r for r in reversed(group) if r['raw'].get('event') in ('llm_response', 'tool_response', 'span_end', 'execution_end')), None)
            request = _data(req or first)
            response = _data(res) if res else {}
            failed = any('error' in e for e in events) or (isinstance(response.get('status'), int) and response['status'] >= 400)
            failed = failed or any(r['raw'].get('data', {}).get('status') == 'failed' for r in group if isinstance(r['raw'].get('data'), dict))
            if any(e.startswith('llm_') for e in events):
                kind = 'chat'; title = request.get('model') or response.get('model') or 'LLM'
            elif request.get('kind') == 'tool':
                kind = 'tool'; title = request.get('name') or 'Tool'
            elif any(e.startswith('tool_') for e in events) and request.get('host'):
                kind = 'sdk' if request.get('purpose') == 'evaluation' else 'http'
                title = f"{request.get('method', 'HTTP')} {request.get('host', '')}{request.get('path', '')}"
            elif first['file'].endswith('framework.jsonl'):
                kind = 'callback'; title = request.get('name') or events[0]
            elif first['raw'].get('source') == 'sdk':
                kind = 'sdk'; title = events[0]
            else:
                kind = 'event'; title = events[0]
            tags = [kind]
            if kind == 'chat' and _contains_tool(response.get('payload')):
                tags.append('tool_call')
            span_id = request.get('framework_span_id')
            related = spans.get(span_id, []) if span_id else []
            folder = first['file'].rsplit('/', 1)[0]
            evidence = 'artifact_directory' if folder in self.contexts else None
            if related:
                folders = {r['file'].rsplit('/', 1)[0] for r in related}
                if len(folders) == 1:
                    folder = next(iter(folders)); evidence = 'framework_span_id'
            context = self.contexts.get(folder)
            if context is None:
                input_id, case_id = request.get('input_id'), request.get('case_id')
                candidates = [c for c in self.contexts.values() if input_id and c['input_id'] == input_id
                              and (not case_id or c['case_id'] == case_id)]
                if len(candidates) == 1:
                    context = candidates[0]; folder = context['folder']; evidence = 'record_input_id'
            started = (req or first)['raw'].get('timestamp')
            ended = res['raw'].get('timestamp') if res else None
            duration = response.get('latency_ms')
            if duration is None and stamp(started) is not None and stamp(ended) is not None:
                duration = max(0, (stamp(ended) - stamp(started)) * 1000)
            complete = 'complete' if req and res else 'missing_response' if req else 'event_only'
            if 'tool_request' in events and not request.get('call_id'):
                complete = 'legacy_address_only'
            status = 'failed' if failed else 'complete' if res else 'recorded' if not req else 'pending'
            if complete == 'legacy_address_only':
                status = 'unknown'
            self.rows.append({'id': identifier, 'kind': kind, 'tags': tags, 'title': title,
                'timestamp': started, 'time_basis': 'recorded', 'ended': ended, 'duration_ms': duration,
                'status': status, 'record_count': len(group), 'chunk_count': events.count('llm_chunk'),
                'input_id': context.get('input_id') if context else None,
                'case_id': context.get('case_id') if context else request.get('case_id'),
                'attempt_id': request.get('attempt_id'),
                'association_status': 'input_exact' if context else 'case_only' if request.get('case_id') else 'unknown',
                'link_evidence': evidence if context else None, 'completeness': complete,
                'call_id': request.get('call_id'), 'framework_span_id': span_id or request.get('span_id'),
                'parent_span_id': request.get('parent_span_id'), 'invocation_id': request.get('invocation_id'),
                'native_session_id': request.get('native_session_id'),
                'tool_call_id': request.get('tool_call_id'), 'purpose': request.get('purpose', 'unknown'),
                'artifact_directory': folder if context else None,
                'destination': request.get('host'), '_context': folder if context else None,
                '_request': req or (first if not res else None), '_response': res, '_callbacks': related})

        link_tools(self.rows, self.contexts)
        link_native_calls(self.rows, self.contexts)
        def coverage(rows):
            return {'requests': len(rows),
                'paired': sum(r['completeness'] == 'complete' for r in rows),
                'case_identified': sum(bool(r.get('case_id')) for r in rows),
                'input_identified': sum(bool(r.get('input_id')) for r in rows),
                'framework_linked': sum(bool(r['_callbacks']) for r in rows),
                'emitted_tool_links': sum(link['status'] == 'exact' for r in rows for link in r.get('tool_relations', []))}
        chats = [r for r in self.rows if r['kind'] == 'chat']
        wire = [r for r in self.rows if r['kind'] in ('chat', 'http') and r.get('call_id')]
        linked = sum(bool(r['_callbacks']) for r in wire)
        self.correlation = {'requests': len(wire), 'linked': linked, 'uncorrelated': len(wire) - linked,
            'status': 'captured' if wire else 'no_requests_observed', 'model': coverage(chats),
            'http': coverage([r for r in wire if r['kind'] == 'http']),
            'model_purposes': dict(Counter(r['purpose'] for r in chats))}
        if chats and self.correlation['model']['input_identified'] < len(chats):
            self.warnings.append(f"{len(chats) - self.correlation['model']['input_identified']}/{len(chats)} model requests have no confirmed Input; Case identity and HTTP pairing are reported separately.")

        labels = {'case.json': ('case', 'SDK Case'), 'input.json': ('case', 'SDK Input'),
                  'mapped-input.json': ('input', 'Input passed to the Agent'), 'request.json': ('input', 'Agent invocation'),
                  'result.json': ('output', 'Agent output'), 'submission.json': ('submission', 'SDK submission'),
                  'report.json': ('judge', 'Judge report'),
                  'file-evidence.json': ('files', 'SDK file changes and diff'),
                  'workspace-artifacts.json': ('files', 'Final changed-file exports'),
                  'workspace.json': ('files', 'Initial workspace contract')}
        for name, artifact in self.artifacts.items():
            if name.startswith('evaluation/workspace-files/'):
                kind, title = 'files', 'Exported file ' + Path(name).stem[:12]
                listing = self.artifacts.get('evaluation/workspace-artifacts.json', {}).get('value') or {}
                title = next((item['path'] for item in listing.get('files', [])
                              if 'evaluation/' + item.get('artifact', '') == name), title)
            elif Path(name).name in labels:
                kind, title = labels[Path(name).name]
            else:
                continue
            identifier = _id('artifact:' + name)
            context = self.contexts.get(name.rsplit('/', 1)[0])
            identity = artifact['value'] if isinstance(artifact['value'], dict) else {}
            recorded = artifact_events.get(name)
            self.groups[identifier] = [{'file': name, 'line': None, 'raw': artifact['value']}]
            if recorded:
                self.groups[identifier].append(recorded)
            self.rows.append({'id': identifier, 'kind': kind, 'tags': [kind], 'title': title,
                'timestamp': recorded['raw'].get('timestamp') if recorded else artifact['timestamp'],
                'time_basis': 'recorded' if recorded else 'file_mtime', 'duration_ms': None,
                'status': 'recorded', 'record_count': len(self.groups[identifier]), 'chunk_count': 0,
                'input_id': context.get('input_id') if context else None,
                'case_id': context.get('case_id') if context else identity.get('case_id'),
                'link_evidence': 'artifact_directory' if context else None, 'completeness': 'snapshot',
                '_artifact': name, '_context': context['folder'] if context else None})
        self.rows.sort(key=lambda r: (_time_order(r['timestamp']), r['id']))
        self.by_id = {r['id']: r for r in self.rows}
        self.total_records = len(records)
        self.revision = _id(json.dumps(files))

    def public(self, row):
        return {k: v for k, v in row.items() if not k.startswith('_')}

    def detail(self, identifier):
        row = self.by_id[identifier]
        context = self.contexts.get(row.get('_context'))
        if context:
            context = {**context, 'case': self.artifacts.get('evaluation/case.json', {}).get('value')}
        request = _data(row['_request']) if row.get('_request') else {}
        response = _data(row['_response']) if row.get('_response') else {}
        matches = []
        if context:
            inp = context['input']
            target = inp.get('payload') if isinstance(inp, dict) else inp
            matches = _matches(request.get('payload'), target)
        callbacks = row.get('_callbacks', [])
        return {**self.public(row), 'request': request, 'response': response,
                'artifact': self.artifacts.get(row.get('_artifact'), {}).get('value'),
                'artifact_file': row.get('_artifact'), 'context': context, 'input_matches': matches,
                'callbacks': {'count': len(callbacks),
                    'input': next((r['raw']['data'].get('input') for r in callbacks if r['raw'].get('event') == 'span_start'), None),
                    'output': next((r['raw']['data'].get('output') for r in reversed(callbacks) if r['raw'].get('event') == 'span_end'), None)},
                'related': [self.public(r) for r in self.rows if r['id'] != identifier and
                            row.get('_context') and r.get('_context') == row['_context'] and
                            r['kind'] in ('case', 'input', 'submission', 'output', 'judge')]}

    def query(self, query):
        def arg(key, default=''):
            value = query.get(key, [default])
            return value[0] if isinstance(value, list) else value
        page, size = int(arg('page', '1')), int(arg('page_size', '20'))
        if page < 1 or size not in (10, 20, 50, 100):
            raise ValueError('Invalid page')
        identifier = arg('id')
        if identifier:
            if identifier not in self.by_id:
                raise KeyError('Interaction unavailable')
            if arg('section') in ('records', 'callbacks'):
                group = (self.by_id[identifier].get('_callbacks', []) if arg('section') == 'callbacks'
                         else self.groups.get(identifier, []))
                return {'records': group[(page-1)*size:page*size], 'total': len(group)}
            return self.detail(identifier)
        kinds = set(filter(None, arg('kinds').split(',')))
        needle = arg('q').casefold()
        start, end = stamp(arg('start')), stamp(arg('end'))
        rows = []
        case_ids = {c['case_id'] for c in self.contexts.values() if c['input_id'] == arg('input_id')}
        unassigned = lambda r: (r['kind'] in ('chat', 'http') and not r.get('input_id')
                                and (not arg('input_id') or r.get('case_id') in case_ids))
        for row in self.rows:
            if kinds and not kinds.intersection(row['tags']): continue
            if arg('status') and row['status'] != arg('status'): continue
            if arg('input_scope') == 'unassigned':
                if not unassigned(row): continue
            elif arg('input_id') and row.get('input_id') != arg('input_id'): continue
            at = stamp(row['timestamp'])
            if start is not None and (at is None or at < start): continue
            if end is not None and (at is None or at > end): continue
            if needle:
                searchable = [self.public(row), self.groups.get(row['id'], []), self.artifacts.get(row.get('_artifact'))]
                if needle not in json.dumps(searchable, ensure_ascii=False).casefold(): continue
            rows.append(row)
        return {'items': [self.public(r) for r in rows[(page-1)*size:page*size]], 'total': len(rows),
                'page': page, 'page_size': size, 'revision': self.revision,
                'unassigned_request_count': sum(unassigned(r) for r in self.rows),
                'total_interactions': len(self.rows), 'total_records': self.total_records,
                'kinds': dict(Counter(r['kind'] for r in self.rows)),
                'inputs': [{'input_id': c['input_id'], 'case_id': c['case_id']} for c in self.contexts.values()],
                'origin': next((r['timestamp'] for r in self.rows if stamp(r['timestamp']) is not None), None),
                'warnings': self.warnings, 'correlation': self.correlation}


def interactions(directory, query):
    root = Path(directory).resolve(strict=True)
    files = _files(root)
    signature = tuple(files)
    with _LOCK:
        cached = _CACHE.get(str(root))
        if cached is None or cached[0] != signature:
            cached = (signature, InteractionIndex(root, files))
            _CACHE[str(root)] = cached
        _CACHE.move_to_end(str(root))
        while len(_CACHE) > 4:
            _CACHE.popitem(last=False)
    return cached[1].query(query)


if __name__ == '__main__':
    import sys
    # Vite calls this same index with shell=False; normal CLI uses it in-process.
    print(json.dumps(interactions(sys.argv[1], json.loads(sys.argv[2])), ensure_ascii=False))
