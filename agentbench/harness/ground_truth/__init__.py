"""Ground truth discovery results shared by Suite and Benchmark views."""
from .files import GroundTruthError, label
from .manifests import MANIFEST_SCHEMA, load_manifest, registered_units
from .matching import aggregate


def _summary(defects, status=None):
    n = len(defects)
    hit = sum(d['score'] == 1 for d in defects)
    pending = sum(d['score'] is None for d in defects)
    return {'status': status or ('empty' if not n else 'not_assessed' if pending == n and not any(d['assessment_count'] for d in defects)
                                else 'partially_assessed' if pending else 'assessed'),
            'defect_count': n, 'assessed_defect_count': n-pending,
            'discovered_defect_count': hit, 'pending_defect_count': pending,
            'assessment_count': sum(d['assessment_count'] for d in defects),
            'discovery_rate': hit/n if n and not pending else None,
            'discovery_bounds': [hit/n, (hit+pending)/n] if n else None}


def benchmark_ground_truth(project_root, suite_records, agent_ids, *, include_unrun_agents=True):
    from .evaluator import read_evaluation
    units, invalid, warnings = registered_units(project_root)
    identifiers = set(agent_ids) | set(units) | (invalid or set()) if include_unrun_agents else set(agent_ids)
    manifests, statuses, records = {}, {}, {}
    for identifier in sorted(identifiers):
        if invalid is None or identifier in invalid:
            statuses[identifier] = 'invalid'
            continue
        try:
            defects = load_manifest(units[identifier], identifier) if identifier in units else None
            if defects is None:
                statuses[identifier] = 'not_configured'
            else:
                manifests[identifier] = defects
        except (ValueError, OSError, KeyError, TypeError) as exc:
            statuses[identifier] = 'invalid'
            warnings.append(f'{identifier}: {exc}')
    for suite in suite_records:
        plan = suite.get('plan')
        if not plan:
            continue
        try:
            from agentbench.harness.session import read_suite
            _, events = read_suite(suite['directory'])
            evaluation = read_evaluation(suite['directory'], plan, events)
            if not evaluation or evaluation.get('status') not in ('completed', 'partial'):
                continue
            for row in evaluation['decisions']:
                records.setdefault((row['agent_id'], row['ground_truth_id']), []).append(row)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            warnings.append(f'GT results unavailable for {plan.get("suite_id")}: {type(exc).__name__}')
    agents = {}
    for identifier in sorted(identifiers):
        details = []
        for defect in manifests.get(identifier, []):
            rows = records.get((identifier, defect['id']), [])
            score = aggregate(r['score'] for r in rows)
            details.append({'id': defect['id'], 'title': defect['summary'], 'score': score,
                            'judge_detected': None if score is None else bool(score),
                            'status': 'not_assessed' if score is None else 'discovered' if score else 'not_discovered',
                            'assessment_count': len(rows)})
        agents[identifier] = {**_summary(details, statuses.get(identifier)), 'defects': details}
    all_defects = [d for a in agents.values() for d in a['defects']]
    totals = _summary(all_defects, None if all_defects else 'invalid' if 'invalid' in statuses.values()
                      else 'empty' if manifests else 'not_configured')
    totals.update(configured_agent_count=len(manifests),
                  unconfigured_agent_count=sum(s == 'not_configured' for s in statuses.values()),
                  invalid_agent_count=sum(s == 'invalid' for s in statuses.values()))
    return {'totals': totals, 'agents': agents, 'warnings': warnings}
