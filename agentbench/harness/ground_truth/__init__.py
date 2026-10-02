"""Host-only confirmed defects and explicit, version-bound discovery assessments.

Ground truth is read from registered Agent units. Assessments describe saved
history across applicable source revisions; running a new retry does not erase
an earlier valid discovery. These interfaces neither run a matcher nor infer
discovery from execution completion or a Judge's ``issue`` verdict.
"""

from .assessments import ASSESSMENTS_SCHEMA, load_assessments, validate_assessment
from .files import GroundTruthError, file_digest, label
from .manifests import MANIFEST_SCHEMA, load_manifest, registered_units
from agentbench.harness.session.plan import digest_json

__all__ = ['ASSESSMENTS_SCHEMA', 'MANIFEST_SCHEMA', 'GroundTruthError',
           'benchmark_ground_truth', 'digest_json', 'file_digest', 'load_manifest',
           'validate_assessment']


def _summary(defects, status=None):
    known = len(defects)
    assessed = sum(defect['assessed_attempt_count'] > 0 for defect in defects)
    found = sum(defect['judge_detected'] is True for defect in defects)
    partial = any(defect['case_reproduced'] is not None or defect['judge_detected'] is not None
                  for defect in defects)
    return {'status': status or ('empty' if not known else 'assessed' if assessed == known
                                else 'partially_assessed' if partial else 'not_assessed'),
            'defect_count': known, 'assessed_defect_count': assessed,
            'case_reproduced_count': sum(defect['case_reproduced'] is True for defect in defects),
            'discovered_defect_count': found,
            'assessment_count': sum(defect['assessment_count'] for defect in defects),
            'discovery_rate': found / known if known and assessed else None}


def _decision(records, field):
    values = [record[field] for record in records if record[field] is not None]
    return any(values) if values else None


def _defect_summary(defect, records):
    case = _decision(records, 'case_reproduced')
    judge = _decision(records, 'judge_detected')
    assessed = sum(all(record[field] is not None for field in ('case_reproduced', 'judge_detected'))
                   for record in records)
    return {'id': defect['id'], 'title': defect['title'],
            'ground_truth_sha256': defect['ground_truth_sha256'],
            'status': ('discovered' if judge is True else 'not_discovered' if assessed
                       else 'partially_assessed' if case is not None or judge is not None else 'not_assessed'),
            'case_reproduced': case, 'judge_detected': judge,
            'assessment_count': len(records), 'assessed_attempt_count': assessed}


def benchmark_ground_truth(project_root, suite_records, agent_ids):
    """Aggregate validated discoveries for accepted catalog Suites and current manifests.

    Each Suite record contains ``plan``, ``snapshot`` and canonical ``directory``.
    Pass only catalog-accepted Suites; legacy records may use ``plan=None``.
    Unconfigured Agents have a null discovery rate, not a zero success rate.
    Registered Agents with manifests are included even before their first Suite.
    """
    units, invalid_ids, warnings = registered_units(project_root)
    selected = set(agent_ids)
    manifests, statuses = {}, {}
    for identifier in sorted(selected | set(units) | (invalid_ids or set())):
        if invalid_ids is None or identifier in invalid_ids:
            statuses[identifier] = 'invalid'
            continue
        unit = units.get(identifier)
        if unit is None:
            if identifier in selected:
                statuses[identifier] = 'not_configured'
            continue
        try:
            defects = load_manifest(unit, identifier)
            if defects is not None:
                manifests[identifier] = defects
            elif identifier in selected:
                statuses[identifier] = 'not_configured'
        except (GroundTruthError, OSError, ValueError, RecursionError) as error:
            statuses[identifier] = 'invalid'
            reason = str(error) if isinstance(error, GroundTruthError) else 'invalid manifest structure'
            warnings.append(f'Ground truth Agent {label(identifier)}: {reason}')
    defects_by_identity = {(agent_id, defect['id']): defect
                           for agent_id, defects in manifests.items() for defect in defects}
    reviews = {}
    for suite in suite_records:
        accepted, diagnostics = load_assessments(suite, defects_by_identity)
        warnings.extend(diagnostics)
        for record in accepted:
            reviews.setdefault((record['agent_id'], record['ground_truth_id']), []).append(record)
    agents = {}
    for identifier in sorted(set(statuses) | set(manifests)):
        details = [_defect_summary(defect, reviews.get((identifier, defect['id']), []))
                   for defect in manifests.get(identifier, [])]
        agents[identifier] = {**_summary(details, statuses.get(identifier)), 'defects': details}
    configured = len(manifests)
    unconfigured = sum(status == 'not_configured' for status in statuses.values())
    invalid = sum(status == 'invalid' for status in statuses.values())
    all_defects = [defect for agent in agents.values() for defect in agent['defects']]
    empty_status = 'invalid' if invalid else 'empty' if configured else 'not_configured'
    totals = _summary(all_defects, empty_status if not all_defects else None)
    totals.update(configured_agent_count=configured, unconfigured_agent_count=unconfigured,
                  invalid_agent_count=invalid)
    return {'totals': totals, 'agents': agents, 'warnings': warnings}
