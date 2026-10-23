"""Post-run, provider-neutral GT comparison over saved Suite evidence.

Automatic results are provisional. This module never modifies GT observations,
SDK reports, or the legacy human assessments file.
"""
import json
import os
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone

from agentbench.harness.session import read_suite
from agentbench.harness.session.plan import digest_json
from agentbench.observe.store import environment_secrets, redact
from agentbench.sdk.common.artifacts import Artifacts
from .manifests import registered_units, load_manifest
from .files import read_bytes, read_json, within, file_digest
from .matching import load_rules, reproduction, detection, summarize, SYSTEM, DETECTION_SYSTEM
from .reviews import eligible_defects, configuration_digest


def evidence_for(api, *, limit):
    """Read only execution files; never leak the SDK verdict into stage one."""
    evidence, hashes, size = {}, {}, 0
    folders = [f for f in api.outputs() if f.startswith('evaluation/inputs/')]
    if not folders:
        raise ValueError('No execution inputs available')
    for folder in folders:
        for required in ('input.json', 'result.json'):
            api.file(f'{folder}/{required}')
        for name in ('input.json', 'result.json', 'framework.jsonl', 'spans.jsonl',
                     'otel-status.json', 'capture-status.json', 'file-evidence.json'):
            relative = f'{folder}/{name}'
            try:
                data = read_bytes(api.file(relative), limit=limit)
            except FileNotFoundError:
                continue
            size += len(data)
            if size > limit:
                raise ValueError('Execution evidence exceeds GT context limit; no truncation performed')
            import hashlib
            hashes[relative] = hashlib.sha256(data).hexdigest()
            evidence['exec:' + relative] = data.decode('utf-8')
    return evidence, hashes


def _model(environ):
    # Reuse ABB's existing OpenAI-compatible transport without its Judge semantics.
    from agentbench.sdk.plugin.local.relay import judge_model
    configured = {k: v for k, v in environ.items() if not k.startswith('ABB_LOCAL_JUDGE_')}
    for suffix in ('BASE_URL', 'MODEL', 'API_KEY'):
        if environ.get('ABB_GT_' + suffix):
            configured['ABB_LOCAL_JUDGE_' + suffix] = environ['ABB_GT_' + suffix]
    return judge_model(configured)


def evaluate_suite(directory, project_root, *, environ=None, output=print, ask=None):
    from agentbench.observe.suite_reader import persisted_snapshot
    from agentbench.observe.view_api import SuiteRunCatalogAPI
    from agentbench.sdk.plugin.local.relay import ask_model
    from filelock import FileLock
    directory = Path(directory).resolve()
    environ = dict(os.environ if environ is None else environ)
    gt_root = within(directory, directory / 'ground_truth')
    gt_root.mkdir(exist_ok=True)
    with FileLock(str(gt_root / '.evaluation.lock'), timeout=0):
        return _evaluate(directory, project_root, environ, output, ask or ask_model,
                         persisted_snapshot, SuiteRunCatalogAPI)


def _evaluate(directory, project_root, environ, output, ask, snapshot_reader, catalog_type):
    plan, events = read_suite(directory)
    snapshot = snapshot_reader(directory / 'events.json')
    if snapshot.get('state') in ('running', 'queued'):
        raise ValueError('Finish the Suite before GT matching')
    evaluation_id = 'gt_' + uuid4().hex[:16]
    destination = within(directory, directory / 'ground_truth' / 'evaluations' / evaluation_id)
    files = Artifacts(destination, environ=environ)
    units, _, warnings = registered_units(project_root)
    rows, skipped = [], []
    limit = int(environ.get('ABB_GT_MAX_BYTES', '240000'))
    budget = int(environ.get('ABB_GT_MAX_CALLS', '200'))
    if limit < 1 or budget < 1:
        raise ValueError('GT context and call limits must be positive')
    summary = {'schema': 'abb.gt.evaluation.v1', 'evaluation_id': evaluation_id,
               'suite_id': plan['suite_id'], 'status': 'running', 'provisional': True,
               'human_review_status': 'pending', 'created_at': datetime.now(timezone.utc).isoformat(),
               'suite_sha256': digest_json({'plan': plan, 'events': events}),
               'gt_project_root': str(Path(project_root).resolve()),
               'gt_configuration_sha256': configuration_digest(project_root, [a['agent_id'] for a in plan['agents']]),
               'attempt_policy': 'all_saved_attempts', 'decisions': rows, 'skipped_agents': skipped,
               'warnings': warnings, 'calls': 0, 'max_calls': budget}
    files.save('inputs.json', {'plan': plan, 'snapshot': snapshot})
    def publish():
        summary['scores'] = summarize(rows)
        summary['agents'] = {a: summarize([r for r in rows if r['agent_id'] == a])
                             for a in sorted({r['agent_id'] for r in rows})}
        for name in ('trigger_coverage', 'discovery_coverage'):
            values = [s[name] for s in summary['agents'].values()]
            summary['scores']['macro_' + name] = (sum(values)/len(values)
                if values and all(v is not None for v in values) else None)
        files.save('summary.json', summary)
        Artifacts(directory, environ=environ).save('ground_truth/latest.json', summary)
    publish()
    catalog = catalog_type(directory / 'events.json').entries(snapshot=snapshot)
    model = None
    model_error = None
    secrets = environment_secrets(environ)
    def call(stage, payload, task):
        nonlocal model, model_error
        if summary['calls'] >= budget:
            raise ValueError('GT model-call budget exhausted')
        if model_error:
            raise ValueError(model_error)
        if model is None:
            try:
                model = _model(environ)
            except (ValueError, RuntimeError) as exc:
                model_error = str(exc)
                raise
        system = SYSTEM if stage == 'reproduction' else DETECTION_SYSTEM
        payload = redact(payload, secrets)
        summary['calls'] += 1
        prefix = f'tasks/{task}/{stage}'
        files.save(prefix + '-request.json', {'model': model.model, 'endpoint': model.base_url,
                   'system': system, 'payload': payload, 'prompt_sha256': digest_json(system)})
        reply, _ = ask(model, [], system=system, payload=payload, normalize=lambda v, _: v,
                      on_response=lambda raw: files.save(prefix + '-response.json', raw))
        files.save(prefix + '-parsed.json', reply)
        return reply
    plans = {a['agent_id']: a for a in plan['agents']}
    for job in snapshot['jobs']:
        agent = job['agent_id']
        try:
            defects = load_manifest(units[agent], agent) if agent in units else None
            if not defects:
                skipped.append({'agent_id': agent, 'reason': 'no_gt'})
                output(f'GT: {agent}: skipped (no GT)')
                continue
            rules = load_rules(units[agent], defects)
            defects, exclusions = eligible_defects(units[agent], defects)
            for review in exclusions:
                skipped.append({'agent_id': agent, 'ground_truth_id': review['ground_truth_id'],
                                'reason': 'human_excluded' if review['decision'] == 'excluded' else 'gt_needs_review',
                                'detail': review['reason']})
        except (OSError, ValueError, KeyError, TypeError) as exc:
            warnings.append(f'{agent}: invalid GT or matching rules: {type(exc).__name__}')
            skipped.append({'agent_id': agent, 'reason': 'invalid_gt'})
            continue
        files.save(f'gt/{digest_json(agent)}.json', {'defects': defects, 'rules': rules})
        for defect in defects:
            rule = rules.get(defect['id'])
            if defect['source_sha256'] != plans[agent]['source_sha256']:
                skipped.append({'agent_id': agent, 'ground_truth_id': defect['id'], 'reason': 'source_not_applicable'})
                continue
            candidates = [(c, a) for c in job['cases'] for a in c.get('attempts', [])]
            if not candidates:
                candidates = [({'case_index': None}, {})]
            for case, attempt in candidates:
                row = {'agent_id': agent, 'ground_truth_id': defect['id'],
                       'ground_truth_sha256': defect['ground_truth_sha256'],
                       'rule_sha256': rule.get('rule_sha256') if rule else None,
                       'rule_review_status': rule.get('review_status') if rule else 'missing',
                       'case_index': case['case_index'], 'attempt_id': attempt.get('attempt_id'),
                       'case_reproduced': None, 'judge_detected': None, 'reason': 'pending'}
                rows.append(row)
                # Sequential IDs are collision-free within this evaluation and
                # avoid Windows MAX_PATH failures from nested SHA filenames.
                task = f'{len(rows):06d}'
                try:
                    if not rule:
                        raise ValueError('Matching rule is missing; human scope review required')
                    prepared = case.get('prepared_case') or {}
                    if not prepared.get('artifact_path') or not prepared.get('artifact_sha256'):
                        raise ValueError('Missing retained case identity')
                    case_path = Path(prepared['artifact_path'])
                    if not case_path.is_absolute():
                        case_path = within(directory, directory / case_path)
                    if file_digest(case_path) != prepared['artifact_sha256']:
                        raise ValueError('Retained case has changed')
                    row['case_sha256'] = prepared['artifact_sha256']
                    result = attempt.get('result') or {}
                    from agentbench.harness.session.attempts import execution_status
                    if (attempt.get('execution_status') or execution_status(result)) != 'completed':
                        raise ValueError('Execution incomplete; not a negative match')
                    states = [attempt, result, result.get('artifacts') or {}]
                    if any(s.get('host_acceptance') == 'rejected' or s.get('evidence_status') in
                           ('missing', 'failed', 'invalid') for s in states):
                        raise ValueError('Rejected or missing execution evidence')
                    matches = [(api, meta) for api, meta in catalog.values()
                               if meta.get('agent') == agent and meta.get('case_index') == case['case_index']
                               and meta.get('attempt_id') == attempt.get('attempt_id')]
                    if len(matches) != 1:
                        raise ValueError('No unambiguous saved execution artifact')
                    api, _ = matches[0]
                    evidence, hashes = evidence_for(api, limit=limit)
                    evidence = redact(evidence, secrets)
                    row['evidence_sha256'] = digest_json(hashes)
                    row['result_sha256'] = digest_json(result)
                    files.save(f'tasks/{task}/evidence.json', {'evidence': evidence, 'hashes': hashes})
                    payload = {'rule': rule, 'evidence': evidence}
                    reply = call('reproduction', payload, task)
                    row['case_reproduced'] = reproduction(reply, rule, evidence)
                    row['conditions'] = reply['conditions']
                    row['reason'] = 'assessed'
                    if row['case_reproduced'] is False:
                        row['judge_detected'] = False
                    elif row['case_reproduced'] is True:
                        report = (result.get('benchmark') or {}).get('report')
                        if report:
                            detection_evidence = {**evidence, 'report': report}
                            reply = call('detection', {'rule': rule, 'evidence': detection_evidence}, task)
                            row['judge_detected'] = detection(reply, detection_evidence)
                            row['detection'] = reply
                        else:
                            row['reason'] = 'No method report; detection unknown'
                    # A changing artifact must not yield a confirmed match.
                    if (evidence_for(api, limit=limit)[1] != hashes or
                            file_digest(case_path) != row['case_sha256']):
                        row['case_reproduced'] = row['judge_detected'] = None
                        raise ValueError('Evidence changed during matching')
                except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
                    row['reason'] = str(redact(str(exc), secrets))
                files.save(f'tasks/{task}/decision.json', row)
                publish()
                output(f"GT: {agent} case {case['case_index']} / {defect['id']}: "
                       f"trigger={row['case_reproduced']}, detection={row['judge_detected']}")
    _, current_events = read_suite(directory)
    summary['pending_pair_count'] = sum(r.get('case_reproduced') is None or
                                        r.get('judge_detected') is None for r in rows)
    summary['status'] = ('stale' if current_events != events else
                         'partial' if summary['pending_pair_count'] or warnings else 'completed')
    publish()
    output(f'GT: automatic provisional results saved to {destination}')
    return summary


def read_evaluation(directory, plan, events):
    path = within(directory, directory / 'ground_truth' / 'latest.json')
    if not path.exists():
        return None
    value = read_json(path)
    if value.get('schema') != 'abb.gt.evaluation.v1' or value.get('suite_id') != plan['suite_id']:
        raise ValueError('Invalid GT evaluation identity')
    if value.get('suite_sha256') != digest_json({'plan': plan, 'events': events}):
        value = {**value, 'status': 'stale'}
    root = value.get('gt_project_root')
    if not root or value.get('gt_configuration_sha256') != configuration_digest(
            Path(root), [a['agent_id'] for a in plan['agents']]):
        value = {**value, 'status': 'stale'}
    return value
