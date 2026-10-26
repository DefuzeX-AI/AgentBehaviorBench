import json
from pathlib import Path
from datetime import datetime, timezone
from agentbench.harness.ground_truth.manifests import load_manifest
from agentbench.harness.ground_truth.reviews import eligible_defects
from agentbench.harness.ground_truth.matching import load_rules

unit = Path('resources/agents/55-garmin-ai-coach').resolve()
stamp = datetime.now(timezone.utc).isoformat()
original = (unit / 'ground_truth/manifest.json').read_bytes()
race = 'december-race-taper-delayed-beyond-race-window'
path = unit / 'ground_truth/reviews.json'
doc = json.loads(path.read_text(encoding='utf-8'))
for review in doc['reviews']:
    if review['decision'] != 'needs_review':
        raise RuntimeError('Do not overwrite a later review')
    review['previous_review'] = dict(review)
    approved = review['ground_truth_id'] == race
    review.update(decision='approved' if approved else 'excluded',
        reviewed_by='user (this conversation)', reviewed_at=stamp,
        user_decision='比赛日期和周次矛盾这条纳入GT，前面默认日期那条先不算',
        reason=('User approved the explicit contradiction between the supplied race date and the forward week numbering/pre-race schedule. A 12–24 week planning horizon alone is not a defect.' if approved else
                'User excluded this candidate for now: interpreting undated indicators as part of a dated snapshot is ambiguous. No demonstrated downstream decision error. Preserve evidence for possible future investigation.'))
path.write_text(json.dumps(doc, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
path = unit / 'ground_truth/matching.json'
doc = json.loads(path.read_text(encoding='utf-8'))
for rule in doc['rules']:
    approved = rule['ground_truth_id'] == race
    rule.update(review_status='approved' if approved else 'excluded',
                reviewed_by='user (this conversation)', reviewed_at=stamp)
    if approved:
        rule['revision'] += 1
        rule['scope'] = 'Explicit inconsistency between a supplied race date and the forward week numbering and pre-race schedule'
        rule['conditions'][1]['text'] = (
            "The final season plan explicitly maps the supplied race date to a forward week number inconsistent with the supplied current date, and places that race's pre-race peak/taper beyond its actual race window, without a reconciling calendar mapping. A generic 12–24 week horizon, ambiguous week origins, unnamed later peaks, and explicitly post-race training do not count.")
        rule['review_note'] = 'User approved this calendar contradiction, not long-horizon planning itself. Original reproduction evidence is unchanged; variants still require evidence-based matching.'
    else:
        rule['review_note'] = 'User excluded for now because a shared snapshot date is a plausible interpretation. Original evidence retained; not eligible for scoring.'
path.write_text(json.dumps(doc, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
defects = load_manifest(unit, 'garmin-ai-coach')
eligible, excluded = eligible_defects(unit, defects)
assert [d['id'] for d in eligible] == [race]
assert len(excluded) == 1
assert load_rules(unit, defects)[race]['review_status'] == 'approved'
assert (unit / 'ground_truth/manifest.json').read_bytes() == original
print('Garmin: race-calendar GT approved; default-date candidate excluded for now. Original evidence unchanged.')
