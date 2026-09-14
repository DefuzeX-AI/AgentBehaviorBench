"""Read-only APIs for one bound observe/evaluate artifact directory."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path


def suite_jobs(events):
    """Build stable Agent aggregates with independent, concurrent Case state."""
    start = next((e for e in events if isinstance(e, dict) and e.get('event') == 'run_started'), {})
    selected = start.get('selected_agent_ids', [])
    selected = selected if isinstance(selected, list) else []
    counts = start.get('selected_case_counts') or {}
    counts = counts if isinstance(counts, dict) else {}
    terminal = {'succeeded', 'failed', 'cancelled', 'skipped'}
    jobs = {agent: {'agent_id': agent, 'job_id': None, 'registration_index': index,
                    'status': 'queued', 'generation_status': 'queued', 'cases': []}
            for index, agent in enumerate(selected) if isinstance(agent, str)}

    def ensure_cases(job, count):
        if type(count) is not int or count < 0:
            return
        while len(job['cases']) < count:
            job['cases'].append({'agent_id': job['agent_id'], 'agent_job_id': job['job_id'],
                                 'job_id': None, 'case_index': len(job['cases']), 'case_id': None,
                                 'status': 'queued', 'phase': 'execute', 'stage': None,
                                 'artifact_run_id': None, 'result': None})

    def update_case(job, data, *, status=None, result=None):
        index = data.get('case_index')
        if type(index) is not int or index < 0:
            return
        ensure_cases(job, index + 1)
        case = job['cases'][index]
        for key in ('job_id', 'agent_job_id', 'case_id', 'artifact_run_id', 'stage'):
            if data.get(key) is not None:
                case[key] = data[key]
        case['agent_job_id'] = case['agent_job_id'] or job['job_id']
        if status is not None:
            case['status'] = status
        if result is not None:
            case['result'] = result

    for job in jobs.values():
        ensure_cases(job, counts.get(job['agent_id'], 1))
    for event in events:
        if not isinstance(event, dict):
            continue
        kind = event.get('event')
        if kind in {'suite_failed', 'suite_completed'}:
            status = 'cancelled' if kind == 'suite_failed' else 'skipped'
            for job in jobs.values():
                if job['status'] not in terminal:
                    job['status'] = status
                for case in job['cases']:
                    if case['status'] not in terminal:
                        case['status'] = status
            continue
        job = jobs.get(event.get('agent_id'))
        if job is None:
            continue
        if kind in {'agent_queued', 'agent_started', 'agent_completed'} or event.get('phase') == 'generate':
            if event.get('job_id') is not None:
                job['job_id'] = event['job_id']
        elif event.get('agent_job_id') is not None:
            job['job_id'] = event['agent_job_id']
        if event.get('registration_index') is not None:
            job['registration_index'] = event['registration_index']
        ensure_cases(job, event.get('requested_case_count', 0))
        if kind == 'agent_queued':
            job['status'] = 'queued'
        elif kind == 'agent_started':
            job['status'] = 'running'
        elif kind == 'progress' and (event.get('phase') == 'generate' or event.get('stage') == 'case_generation'):
            job['generation_status'] = {'started': 'running', 'succeeded': 'succeeded', 'failed': 'failed'}.get(event.get('status'), 'running')
            job['status'] = 'running'
        elif kind == 'case_queued':
            update_case(job, event, status='queued')
        elif kind == 'case_started':
            update_case(job, event, status='running')
            job['status'] = 'running'
        elif kind == 'case_completed':
            result = event.get('case_result') or {}
            if isinstance(result, dict):
                update_case(job, {**event, **result}, status=event.get('status') or result.get('status', 'failed'), result=result)
        elif kind in {'progress', 'step_started', 'step_completed', 'step_failed'}:
            index = event.get('case_index')
            if type(index) is int and index >= 0:
                ensure_cases(job, index + 1)
                current = job['cases'][index]['status']
                update_case(job, event, status=current if current in terminal else 'running')
            if job['status'] not in terminal:
                job['status'] = 'running'
        elif kind == 'agent_completed':
            item = event.get('item') or {}
            if not isinstance(item, dict):
                continue
            ensure_cases(job, item.get('requested_case_count', 0))
            for case_result in item.get('case_results', []):
                if isinstance(case_result, dict):
                    update_case(job, case_result, status=case_result.get('status', 'failed'), result=case_result)
            error = item.get('error') or item.get('preparation_error') or {}
            error_type = error.get('type', error.get('error_type')) if isinstance(error, dict) else None
            status = event.get('status') or item.get('status')
            if status not in terminal:
                status = ('cancelled' if error_type in {'RunCancelled', 'KeyboardInterrupt'} else
                          'failed' if error or any(case['status'] == 'failed' for case in job['cases']) else 'succeeded')
            job['status'] = status
            for case in job['cases']:
                if case['status'] not in terminal:
                    case['status'] = 'cancelled' if status == 'cancelled' else 'skipped'
    for job in jobs.values():
        for case in job['cases']:
            case['agent_job_id'] = case['agent_job_id'] or job['job_id']
        job['counts'] = {status: sum(case['status'] == status for case in job['cases'])
                         for status in ('queued', 'running', 'succeeded', 'failed', 'cancelled', 'skipped')}
    return list(jobs.values())


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
        public = (self.read('run.json') or {}).get('evaluation_result') or {}
        return {**{key: self.read('evaluation/' + name) for key, name in {
            'manifest': 'manifest.json', 'process': 'process.json', 'case': 'case.json',
            'judge': 'judge/report.json', 'error': 'error.json'}.items()},
            'public_result': public, 'execution_status': (self.read('run.json') or {}).get('status'),
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
        if route == 'metadata':
            return self.read('run.json') or {}
        if route == 'interactions':
            from .interactions import interactions
            return interactions(self.directory, query)
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


class SuiteRunCatalogAPI:
    """Expose only artifact directories registered in the selected suite.

    Paths come from host-side SDK progress records, never HTTP parameters.
    Each directory must identify a selected Agent and a valid ABB artifact run;
    RunViewAPI confines every subsequent file read to that directory.
    """

    def __init__(self, result_log):
        self.result_log = Path(result_log).resolve()

    def entries(self, events=None):
        if events is None:
            events = json.loads(self.result_log.read_text(encoding='utf-8'))
        if not isinstance(events, list):
            raise ValueError('Expected suite events')
        selected = next((e.get('selected_agent_ids', []) for e in events
                         if isinstance(e, dict) and e.get('event') == 'run_started'), [])
        references = []
        for event in events:
            if not isinstance(event, dict):
                continue
            if event.get('event') == 'progress':
                references.append((event.get('agent_id'), event.get('artifact_directory'), event))
            elif event.get('event') in {'agent_completed', 'case_completed'}:
                item = event.get('item') or {}
                if event.get('event') == 'case_completed':
                    case = event.get('case_result') or {}
                    item = {'benchmarks': [case.get('benchmark')]} if isinstance(case, dict) else {}
                if not isinstance(item, dict) or not isinstance(item.get('benchmarks', []), list):
                    continue
                for result in item.get('benchmarks', []):
                    if not isinstance(result, dict):
                        continue
                    report = result.get('report') or {}
                    if not isinstance(report, dict):
                        continue
                    extensions = report.get('extensions') or {}
                    if not isinstance(extensions, dict):
                        continue
                    references.append((event.get('agent_id'),
                                       extensions.get('abb_artifact_directory'),
                                       {**event, **{key: extensions[key] for key in
                                        ('case_id', 'case_index', 'artifact_run_id') if key in extensions}}))
        entries = {}
        for agent_id, value, identity in references:
            if agent_id not in selected or not isinstance(value, str):
                continue
            directory = Path(value)
            if not directory.is_absolute() or directory.is_symlink():
                continue
            try:
                api = RunViewAPI(directory)
                metadata = api.read('run.json')
                if (not isinstance(metadata, dict) or metadata.get('agent_id') != agent_id
                    or metadata.get('run_id') != directory.name
                    or metadata.get('schema') not in ('abb.observe.run.v1', 'abb.evaluate.run.v1')
                    or not re.fullmatch(r'[a-zA-Z0-9_-]+', directory.name)):
                    continue
                updated = datetime.fromtimestamp(api.file('run.json').stat().st_mtime, timezone.utc).isoformat()
                details = dict(entries.get(directory.name, (None, {}))[1])
                details.update({'id': directory.name, 'agent': agent_id,
                                'status': metadata.get('status'), 'updated': updated})
                for key in ('suite_id', 'job_id', 'agent_job_id', 'registration_index', 'case_index', 'case_id', 'artifact_run_id'):
                    candidate = metadata.get(key)
                    if candidate is None:
                        candidate = identity.get(key)
                    if candidate is not None:
                        details[key] = candidate
                entries[directory.name] = (api, details)
            except (OSError, ValueError):
                continue
        return entries

    def route(self, path, query):
        events = json.loads(self.result_log.read_text(encoding='utf-8'))
        entries = self.entries(events)
        if path == '/api/observe/runs':
            jobs = suite_jobs(events)
            order = {job['agent_id']: index for index, job in enumerate(jobs)}
            runs = sorted((entry[1] for entry in entries.values()),
                          key=lambda run: (order.get(run['agent'], len(order)),
                                           run.get('case_index') or 0, run['id']))
            return {'runs': runs, 'jobs': jobs, 'default_run': runs[0]['id'] if runs else None}
        match = re.fullmatch(r'/api/observe/runs/([a-zA-Z0-9_-]+)/(.+)', path)
        if not match or match[1] not in entries:
            raise ValueError('Run not registered in this suite')
        return entries[match[1]][0].route(path, query)
