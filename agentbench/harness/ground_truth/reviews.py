"""Human eligibility decisions, separate from immutable reproduction records."""
from .files import GroundTruthError, read_json, within, file_digest
from .manifests import registered_units
from agentbench.harness.session.plan import digest_json


def eligible_defects(unit, defects):
    path = within(unit, unit / 'ground_truth' / 'reviews.json')
    if not path.exists():
        return defects, []
    doc = read_json(path)
    if doc.get('schema') != 'abb.gt.reviews.v1':
        raise GroundTruthError('Unsupported GT reviews')
    known = {d['id']: d for d in defects}
    excluded, seen = [], set()
    for review in doc.get('reviews', []):
        key = review.get('ground_truth_id')
        if key not in known or key in seen:
            raise GroundTruthError('Unknown or duplicate GT review')
        seen.add(key)
        if review.get('ground_truth_sha256') != known[key]['ground_truth_sha256']:
            raise GroundTruthError('GT review refers to changed evidence')
        if review.get('decision') not in {'excluded', 'needs_review', 'approved'} or not all(
                isinstance(review.get(k), str) and review[k].strip()
                for k in ('reason', 'reviewed_by', 'reviewed_at')):
            raise GroundTruthError('Invalid GT exclusion')
        if review['decision'] != 'approved':
            excluded.append(review)
    excluded_ids = {r['ground_truth_id'] for r in excluded}
    return [d for d in defects if d['id'] not in excluded_ids], excluded


def configuration_digest(project_root, agents):
    units, invalid, warnings = registered_units(project_root)
    values = {'invalid': sorted(invalid or []), 'warnings': warnings, 'agents': {}}
    for agent in sorted(set(agents)):
        unit = units.get(agent)
        values['agents'][agent] = None if unit is None else {
            name: file_digest(path) if path.exists() else None
            for name in ('manifest.json', 'matching.json', 'reviews.json')
            for path in [within(unit, unit / 'ground_truth' / name)]}
    return digest_json(values)
