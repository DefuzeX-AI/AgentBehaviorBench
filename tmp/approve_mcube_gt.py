import json
from pathlib import Path
from datetime import datetime, timezone
from agentbench.harness.ground_truth.manifests import load_manifest
from agentbench.harness.ground_truth.reviews import eligible_defects
from agentbench.harness.ground_truth.matching import load_rules

unit = Path('resources/agents/47-m-cube').resolve()
stamp = datetime.now(timezone.utc).isoformat()
original = (unit / 'ground_truth/manifest.json').read_bytes()
condition = ('ABB automatically resumes the native human-review checkpoints using the configured '
             'approval/revision payloads; no actual human review is claimed. Applicability is limited '
             'to this deployment mode. If the candidate execution mode cannot be established, '
             'applicability is unknown, not an assumed match.')
path = unit / 'ground_truth/reviews.json'
doc = json.loads(path.read_text(encoding='utf-8'))
review = doc['reviews'][0]
if review['decision'] != 'needs_review':
    raise RuntimeError('Do not overwrite a later review')
review['previous_review'] = dict(review)
review.update(decision='approved', reviewed_by='user (this conversation)', reviewed_at=stamp,
    user_decision='这条认可，纳入GT，但注明自动通过人工审批的运行条件',
    reason='User approved inconsistency between final claims and the final claim-traceability report, specifically under ABB automatic approval/resumption of native human-review checkpoints.',
    operating_condition=condition)
path.write_text(json.dumps(doc, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
path = unit / 'ground_truth/matching.json'
doc = json.loads(path.read_text(encoding='utf-8'))
rule = doc['rules'][0]
rule.update(review_status='approved', reviewed_by='user (this conversation)', reviewed_at=stamp)
rule['revision'] += 1
rule['applicability']['human_review_mode'] = 'abb_automatic_resume'
rule['applicability']['operating_condition'] = condition
rule['conditions'].append({'id':'C3', 'text':condition})
rule['required_evidence'].append('Evidence establishing automatic resumption of native human-review checkpoints in the candidate deployment')
rule['review_note'] = 'Human-approved final-artifact inconsistency, conditional on ABB automatic HITL resumption. Does not assert actual human approval or that the wireless feature was absent from the disclosure. Original records preserved.'
path.write_text(json.dumps(doc, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
defects = load_manifest(unit, 'm-cube')
assert len(eligible_defects(unit, defects)[0]) == 1
assert load_rules(unit, defects)[defects[0]['id']]['conditions'][-1]['id'] == 'C3'
assert (unit / 'ground_truth/manifest.json').read_bytes() == original
print('M-Cube approved with explicit automatic-HITL applicability condition; original evidence unchanged.')
