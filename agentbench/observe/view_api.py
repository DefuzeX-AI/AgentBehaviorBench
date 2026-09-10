"""Read-only APIs for one bound observe/evaluate artifact directory."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path


class RunCatalogAPI:
    """Browse sibling runs, confined to the selected artifact root."""

    def __init__(self, directory):
        self.root = directory.resolve().parent
        self.default_run = directory.name

    def run(self, run_id):
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', run_id):
            raise ValueError('Invalid run ID')
        directory = self.root / run_id
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError('Run unavailable')
        api = RunViewAPI(directory)
        if api.directory.parent != self.root or not api.file('run.json').is_file():
            raise ValueError('Run outside root')
        return api

    def route(self, path, query):
        if path == '/api/observe/runs':
            runs = []
            for directory in self.root.iterdir():
                try:
                    api = self.run(directory.name)
                    metadata = api.read('run.json')
                    if not isinstance(metadata, dict):
                        continue
                    updated = datetime.fromtimestamp(api.file('run.json').stat().st_mtime, timezone.utc).isoformat()
                    runs.append({'id': directory.name, 'agent': metadata.get('agent_id'),
                                 'status': metadata.get('status'), 'updated': updated})
                except (OSError, ValueError):
                    continue
            runs.sort(key=lambda run: run['updated'], reverse=True)
            return {'runs': runs, 'default_run': self.default_run}
        match = re.fullmatch(r'/api/observe/runs/([a-zA-Z0-9_-]+)/(.+)', path)
        if not match:
            raise ValueError('Unknown route')
        return self.run(match[1]).route(path, query)


class RunViewAPI:
    def __init__(self, directory):
        self.directory = directory.resolve()
        self.run_id = directory.name

    def file(self, relative):
        path = (self.directory / relative).resolve(strict=True)
        if not path.is_relative_to(self.directory) or path == self.directory:
            raise ValueError('Path outside run')
        return path

    def read(self, relative):
        try:
            return json.loads(self.file(relative).read_text(encoding='utf-8'))
        except FileNotFoundError:
            return None

    def outputs(self):
        folders = [f'{p.name}/output' for p in sorted(self.directory.glob('invocation-*')) if p.is_dir()]
        try:
            inputs = self.file('evaluation/inputs')
        except FileNotFoundError:
            return folders
        return folders + [f'evaluation/inputs/{p.name}' for p in sorted(inputs.iterdir())
                          if p.is_dir() and re.fullmatch(r'\d{4}', p.name)]

    def spans(self):
        spans, statuses, warnings = [], [], []
        for folder in self.outputs():
            status = self.read(f'{folder}/otel-status.json') or {'status': 'running_or_unavailable'}
            statuses.append({'invocation': folder, **status})
            try:
                with self.file(f'{folder}/otel.jsonl').open(encoding='utf-8') as stream:
                    for line in stream:
                        if not line.strip():
                            continue
                        try:
                            row = json.loads(line)
                            if row.get('source') == 'otel' and row.get('event') == 'span':
                                spans.append({**row['data'], 'invocation': folder, 'output_directory': folder})
                        except (ValueError, KeyError):
                            warnings.append(f'{folder}: incomplete OTel line')
            except FileNotFoundError:
                pass
        latest = {}
        for folder in self.outputs():
            try:
                with self.file(f'{folder}/otel-live.jsonl').open(encoding='utf-8') as stream:
                    for line in stream:
                        try:
                            row = json.loads(line)
                            s = {**row['data'], 'invocation': folder, 'output_directory': folder}
                            latest[(s.get('trace_id'), s['span_id'])] = s
                        except (ValueError, KeyError):
                            continue
            except FileNotFoundError:
                pass
        latest.update({(s.get('trace_id'), s['span_id']): s for s in spans})
        return {'spans': list(latest.values()), 'statuses': statuses, 'warnings': warnings}

    def evaluation(self):
        return {**{key: self.read('evaluation/' + name) for key, name in {
            'manifest': 'manifest.json', 'process': 'process.json', 'case': 'case.json',
            'judge': 'judge/report.json', 'error': 'error.json'}.items()},
            'inputs': [{'step': Path(folder).name, **{key: self.read(f'{folder}/{name}.json')
                       for key, name in {'input': 'input', 'result': 'result',
                                         'submission': 'submission', 'evidence': 'evidence'}.items()}}
                       for folder in self.outputs() if folder.startswith('evaluation/')]}

    def events(self, offset):
        if offset < 0:
            raise ValueError('Invalid cursor')
        events, warnings, index = [], [], 0
        for name in ['network.jsonl', *(f'{p}/framework.jsonl' for p in self.outputs())]:
            try:
                with self.file(name).open(encoding='utf-8') as stream:
                    for line in stream:
                        if not line.strip():
                            continue
                        index += 1
                        if index <= offset:
                            continue
                        if len(events) == 100:
                            return {'events': events, 'warnings': warnings, 'next': index - 1}
                        try:
                            events.append({'file': name, 'raw': json.loads(line)})
                        except ValueError:
                            warnings.append(f'{name}: incomplete event')
            except FileNotFoundError:
                pass
        return {'events': events, 'warnings': warnings, 'next': None}

    def route(self, path, query):
        if path == '/api/observe/runs':
            metadata = self.read('run.json') or {}
            return {'runs': [{'id': self.run_id, 'agent': metadata.get('agent_id'),
                             'status': metadata.get('status'), 'updated': None}]}
        prefix = f'/api/observe/runs/{self.run_id}/'
        if not path.startswith(prefix):
            raise ValueError('Run does not match this viewer')
        route = path[len(prefix):]
        if route == 'evaluation':
            return self.evaluation()
        if route == 'events':
            return self.events(int(query.get('offset', ['0'])[0]))
        if route == 'otel':
            return self.spans()
        match = re.fullmatch(r'otel/([0-9a-f]{16})/payload/(input|output|error|metadata|events)', route)
        if match:
            span = next(s for s in self.spans()['spans'] if s['span_id'] == match[1])
            output = self.file(span['output_directory'])
            ref = span['attributes'][f'abb.{match[2]}_ref']
            target = (output / ref).resolve(strict=True)
            if not target.is_relative_to(output):
                raise ValueError('Payload outside output')
            with target.open(encoding='utf-8') as stream:
                payload = [json.loads(line) for line in stream if line.strip()] if match[2] == 'events' else json.load(stream)
            return {'payload': payload}
        raise ValueError('Unknown route')
