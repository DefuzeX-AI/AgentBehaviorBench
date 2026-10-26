import json
from pathlib import Path
from datetime import datetime, timezone
from agentbench.harness.ground_truth.manifests import load_manifest
from agentbench.harness.ground_truth.reviews import eligible_defects
from agentbench.harness.ground_truth.matching import load_rules

unit = Path('resources/agents/52-jobsmith').resolve()
stamp = datetime.now(timezone.utc).isoformat()
manifest_bytes = (unit / 'ground_truth/manifest.json').read_bytes()
path = unit / 'ground_truth/reviews.json'
doc = json.loads(path.read_text(encoding='utf-8'))
review = doc['reviews'][0]
review['previous_review'] = dict(review)
review.update(decision='approved', reviewed_by='user (this conversation)', reviewed_at=stamp,
              user_decision='认可，纳入 GT',
              reason='User confirmed the observed unsupported candidate cloud-deployment claim and the review scope. Job requirements are not evidence of candidate skills; learning intentions, future plans and ordinary wording improvements are excluded.')
path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
path = unit / 'ground_truth/matching.json'
doc = json.loads(path.read_text(encoding='utf-8'))
rule = doc['rules'][0]
rule.update(review_status='approved', reviewed_by='user (this conversation)', reviewed_at=stamp,
            review_note='Human approved the defect and scope on this date. Existing conditions retain the specific cloud-deployment defect; reference records are unchanged. Approval does not assert all possible variants reproduce.')
path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
defects = load_manifest(unit, 'jobsmith')
assert len(eligible_defects(unit, defects)[0]) == 1
assert load_rules(unit, defects)[defects[0]['id']]['review_status'] == 'approved'
assert (unit / 'ground_truth/manifest.json').read_bytes() == manifest_bytes
print('JobSmith: one eligible, human-approved GT; original manifest unchanged.')
