"""Compare saved Judge summaries, then both traces, without executing an Agent."""
import json
import os
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone
from filelock import FileLock

from agentbench.harness.session import read_suite
from agentbench.observe.store import environment_secrets, redact
from agentbench.sdk.common.artifacts import Artifacts
from .files import read_json, within
from .manifests import registered_units, load_manifest
from .matching import SUMMARY_SYSTEM, TRACE_SYSTEM, validate_match, summarize
from .traces import read_trace, read_reference_traces
from .transport import model_config, ask_once

SCHEMA = 'abb.gt.evaluation.v2'
PROTOCOL = 'summary-trace-discovery-v2.1'


def input_state(directory, root, agent_ids):
    """Metadata for cache freshness only; no file hash or source-version gate."""
    units, _, _ = registered_units(root)
    paths = [directory / 'plan.json', directory / 'events.json']
    from agentbench.harness.session.references import _event_paths
    try:
        plan, events = read_suite(directory)
    except (OSError, ValueError, KeyError):
        events = []
    for event in events:
        for referenced in _event_paths(event):
            if referenced.is_dir():
                paths.extend(p for p in referenced.rglob('*') if p.is_file() and 'gt' not in p.parts)
            elif referenced.is_file():
                paths.append(referenced)
    if (directory / 'cases').exists():
        paths.extend(p for p in (directory / 'cases').rglob('*') if p.is_file())
    for agent in agent_ids:
        if agent in units:
            gt_root = within(units[agent], units[agent] / 'ground_truth')
            paths.extend(within(gt_root, p) for p in gt_root.rglob('*') if p.is_file())
    states = []
    for path in sorted(set(paths)):
        try:
            stat = path.stat()
            states.append([str(path), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns])
        except FileNotFoundError:
            states.append([str(path), None])
    return states


def read_evaluation(directory, plan, events):
    directory = Path(directory)
    path = within(directory, directory / 'ground_truth/latest.json')
    from .storage import read as read_references
    value = read_references(directory)
    if value is None:
        if not path.exists():
            return None
        value = read_json(path, limit=64 * 1024 * 1024)
    if value.get('schema') != SCHEMA:
        return {'status': 'legacy', 'provisional': True, 'reason': 'Re-evaluate with summary/trace matching'}
    if value.get('suite_id') != plan['suite_id']:
        raise ValueError('GT result belongs to another Suite')
    if (value.get('protocol') != PROTOCOL or value.get('input_state') !=
            input_state(directory, Path(value['gt_project_root']), [a['agent_id'] for a in plan['agents']])):
        return {**value, 'status': 'stale'}
    return value


def evaluate_suite(directory, project_root, *, environ=None, output=print, ask=None):
    from agentbench.observe.suite_reader import persisted_snapshot
    from agentbench.observe.view_api import SuiteRunCatalogAPI
    directory, project_root = Path(directory).resolve(), Path(project_root).resolve()
    environ = dict(os.environ if environ is None else environ)
    plan, _ = read_suite(directory)
    gt_root = directory if plan.get('artifact_layout') == 'agent-trajectories-v1' else within(directory, directory / 'ground_truth')
    gt_root.mkdir(exist_ok=True)
    with FileLock(str(gt_root / '.evaluation.lock'), timeout=0):
        return _evaluate(directory, project_root, environ, output, ask or ask_once,
                         persisted_snapshot, SuiteRunCatalogAPI)


def _evaluate(directory, root, environ, output, ask, snapshot_reader, catalog_type):
    plan, events = read_suite(directory)
    snapshot = snapshot_reader(directory / 'events.json')
    if snapshot.get('state') in ('running', 'queued'):
        raise ValueError('Finish the Suite before GT matching')
    previous = read_evaluation(directory, plan, events)
    settings = {k: v for k, v in environ.items() if k in
                ('ABB_GT_MODEL', 'ABB_GT_BASE_URL', 'ABB_GT_MAX_BYTES', 'ABB_GT_MAX_CALLS')}
    if previous and previous.get('status') in ('completed', 'partial') and previous.get('settings') == settings:
        output('GT: reused saved summary/trace assessment; no new requests')
        return {**previous, 'cache_reused': True, 'new_calls': 0}
    units, _, warnings = registered_units(root)
    catalog = catalog_type(directory / 'events.json').entries(snapshot=snapshot)
    evaluation_id = 'gt_' + uuid4().hex[:16]
    from .storage import agent_roots, publish as publish_references
    roots = agent_roots(directory, plan)
    destination = directory / 'ground_truth/evaluations' / evaluation_id
    files = Artifacts(destination, environ=environ)
    suite_files = Artifacts(directory, environ=environ)
    secrets = environment_secrets(environ)
    rows = []
    summary = {'schema': SCHEMA, 'protocol': PROTOCOL, 'evaluation_id': evaluation_id,
               'suite_id': plan['suite_id'], 'status': 'running', 'provisional': True,
               'created_at': datetime.now(timezone.utc).isoformat(), 'gt_project_root': str(root),
               'input_state': input_state(directory, root, [a['agent_id'] for a in plan['agents']]),
               'settings': settings, 'decisions': rows, 'warnings': warnings, 'skipped_agents': [],
               'calls': 0, 'cache_hits': 0, 'max_calls': int(environ.get('ABB_GT_MAX_CALLS', '200'))}
    limit = int(environ.get('ABB_GT_MAX_BYTES', str(8 * 1024 * 1024)))
    model = None
    calls_dir = directory / 'ground_truth/calls'
    if not roots:
        calls_dir.mkdir(parents=True, exist_ok=True)
    calls = Artifacts(calls_dir, environ=environ)

    def publish():
        summary['scores'] = summarize(rows)
        summary['agents'] = {a: summarize(r for r in rows if r['agent_id'] == a)
                             for a in sorted({r['agent_id'] for r in rows})}
        if roots:
            publish_references(directory, roots, summary, environ)
        else:
            files.save('summary.json', summary)
            suite_files.save('ground_truth/latest.json', summary)

    def call(stage, payload):
        nonlocal model
        system = SUMMARY_SYSTEM if stage == 'summary' else TRACE_SYSTEM
        payload = redact(payload, secrets)
        if len(json.dumps(payload, ensure_ascii=False).encode()) > limit:
            raise ValueError('Matcher context too large; decision remains pending')
        if model is None:
            model = model_config(environ)
        request = {'protocol': PROTOCOL, 'stage': stage, 'system': system, 'payload': payload,
                   'model': model.model, 'endpoint': model.base_url}
        for path in sorted(calls_dir.glob('*.json')):
            cached = read_json(path, limit=64 * 1024 * 1024)
            if cached.get('request') == request:
                summary['cache_hits'] += 1
                if cached.get('state') == 'completed':
                    return cached['reply']
                raise ValueError('Prior matcher request failed or was interrupted; not resubmitted')
        if summary['calls'] >= summary['max_calls']:
            raise ValueError('GT call budget exhausted')
        name = uuid4().hex + '.json'
        record = {'request': request, 'state': 'submitted'}
        calls.save(name, record)  # Journal before dispatch, including uncertain outcomes.
        summary['calls'] += 1
        publish()
        try:
            reply = ask(model, system=system, payload=payload)
            calls.save(name, {**record, 'state': 'completed', 'reply': reply})
            return reply
        except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
            calls.save(name, {**record, 'state': 'failed', 'error': str(redact(str(exc), secrets))})
            raise

    def api_for(agent, case, attempt):
        matches = [api for api, meta in catalog.values()
                   if meta.get('agent') == agent and meta.get('case_index') == case.get('case_index')
                   and meta.get('attempt_id') == attempt.get('attempt_id')]
        return matches[0] if len(matches) == 1 else None

    publish()
    for job in snapshot['jobs']:
        agent = job['agent_id']
        if roots:
            destination = roots[agent] / 'evaluations' / evaluation_id
            files = Artifacts(destination, environ=environ)
            calls_dir = roots[agent] / 'calls'
            calls_dir.mkdir(parents=True, exist_ok=True)
            calls = Artifacts(calls_dir, environ=environ)
        try:
            defects = load_manifest(units[agent], agent) if agent in units else None
        except (OSError, ValueError, KeyError, TypeError) as exc:
            warnings.append(f'{agent}: {exc}')
            continue
        if not defects:
            summary['skipped_agents'].append({'agent_id': agent, 'reason': 'no_gt'})
            continue
        for defect in defects:
            candidates = [(case, attempt) for case in job['cases'] for attempt in (case.get('attempts') or [{}])]
            for case, attempt in candidates or [({}, {})]:
                result = attempt.get('result') or {}
                api = api_for(agent, case, attempt)
                report = (result.get('benchmark') or {}).get('report')
                if not report and api:
                    report = api.read('evaluation/judge/report.json')
                valid_report = isinstance(report, dict) and report.get('status') in ('pass', 'issue') and not report.get('evidence_gaps')
                rejected = any(s.get('host_acceptance') == 'rejected' for s in
                               (attempt, result, result.get('artifacts') or {}))
                findings = report.get('issues', []) if isinstance(report, dict) else []
                if not isinstance(findings, list):
                    findings, valid_report = [], False
                # A report can contain real findings and still leave other findings unknown.
                entries = [(i, finding) for i, finding in enumerate(findings)]
                if not entries or not valid_report or rejected:
                    entries.append((None, None))
                for index, finding in entries:
                    row = {'agent_id': agent, 'ground_truth_id': defect['id'], 'gt_summary': defect['summary'],
                           'case_index': case.get('case_index'), 'attempt_id': attempt.get('attempt_id'),
                           'finding_index': index, 'finding': finding, 'score': None, 'reason': 'pending'}
                    rows.append(row)
                    if finding is None:
                        complete_pass = valid_report and not findings and report.get('status') == 'pass' and not rejected
                        row.update(score=0 if complete_pass else None,
                                   reason='Complete Judge report contains no findings' if complete_pass
                                   else 'Judge report missing, incomplete, rejected, or no saved execution')
                        continue
                    try:
                        if rejected:
                            raise ValueError('Report evidence rejected by host')
                        text = finding.get('message') if isinstance(finding, dict) else finding
                        if not isinstance(text, str) or not text.strip():
                            raise ValueError('Judge finding has no problem summary')
                        payload = {'reference': {'summary': defect['summary'], 'explanation': defect['explanation']},
                                   'finding_summary': text}
                        first = validate_match(call('summary', payload))
                        row['summary_match'] = first
                        if first['match'] is not True:
                            row.update(score=0 if first['match'] is False else None, reason=first['reason'])
                            continue
                        if api is None:
                            raise ValueError('No unambiguous saved execution trace')
                        states = (attempt, result, result.get('artifacts') or {})
                        if any(s.get('evidence_status') in ('missing', 'invalid', 'failed') for s in states):
                            raise ValueError('Captured trace unavailable or invalid')
                        candidate = read_trace(api, limit=limit)
                        reference = read_reference_traces(defect, limit=limit)
                        reference_ids = {e['id'] for t in reference for e in t['events']}
                        candidate_ids = {e['id'] for e in candidate['events']}
                        second_payload = {**payload, 'reference_traces': reference, 'candidate_trace': candidate}
                        evidence_path = f'tasks/{len(rows):06d}/traces.json'
                        files.save(evidence_path, redact(second_payload, secrets))
                        row['trace_evidence_path'] = os.path.relpath(destination / evidence_path, directory).replace('\\', '/')
                        second = validate_match(call('trace', second_payload), reference_ids, candidate_ids)
                        row['trace_match'] = second
                        row['trace_evidence'] = redact({
                            'reference': [e for t in reference for e in t['events'] if e['id'] in second['reference_event_ids']],
                            'candidate': [e for e in candidate['events'] if e['id'] in second['candidate_event_ids']]}, secrets)
                        row.update(score=None if second['match'] is None else int(second['match']), reason=second['reason'])
                    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
                        row.update(score=None, reason=str(redact(str(exc), secrets)))
                    finally:
                        publish()
                    output(f"GT: {agent} / {defect['id']} case {case.get('case_index')}: {row['score']}")
    summary['status'] = 'partial' if summarize(rows)['pending'] or warnings else 'completed'
    if summary['input_state'] != input_state(directory, root, [a['agent_id'] for a in plan['agents']]):
        summary['status'] = 'stale'
    publish()
    output(f'GT: summary/trace results saved to {destination}; calls={summary["calls"]}')
    return summary
