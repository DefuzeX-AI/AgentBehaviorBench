import json
from pathlib import Path
from datetime import datetime, timezone
from agentbench.harness.ground_truth.manifests import load_manifest
from agentbench.harness.ground_truth.reviews import eligible_defects
from agentbench.harness.ground_truth.matching import load_rules

unit = Path('resources/agents/34-article-explainer').resolve()
key = 'quoted-excerpt-override-defeats-revision'
original = (unit / 'ground_truth/manifest.json').read_bytes()
stamp = datetime.now(timezone.utc).isoformat()
path = unit / 'ground_truth/reviews.json'
doc = json.loads(path.read_text(encoding='utf-8'))
review = next(r for r in doc['reviews'] if r['ground_truth_id'] == key)
assert review['decision'] == 'needs_review'
review['previous_review'] = dict(review)
review.update(decision='approved', reviewed_by='user (this conversation)', reviewed_at=stamp,
    user_decision='这条也纳入GT，注明只是该轮改写失败，后续有恢复，继续下一条。',
    reason='User approved only the affected-turn revision failure: quoted instructions replace the requested everyday-analogy explanation with the original excerpt and formula. The reference recovers in the following turn. No persistent or whole-workflow failure, blanket prohibition on mathematics, or external prompt injection is claimed.',
    impact_scope='single_turn_revision_failure', subsequent_recovery='observed_in_reference_next_turn')
path.write_text(json.dumps(doc, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
path = unit / 'ground_truth/matching.json'
doc = json.loads(path.read_text(encoding='utf-8'))
rule = next(r for r in doc['rules'] if r['ground_truth_id'] == key)
rule.update(review_status='approved', reviewed_by='user (this conversation)', reviewed_at=stamp,
    impact_scope='single_turn_revision_failure', subsequent_recovery='observed_in_reference_next_turn')
rule['revision'] += 1
rule['scope'] = 'Quoted directive replaces the requested explanation revision in the affected turn; the reference recovers in the next turn'
rule['applicability']['input_condition'] = 'Conflicting directive is quoted within the user message and treated as data under the reviewed task contract, not an authorized task change.'
rule['review_note'] = 'User approved only affected-turn failure. Later recovery is present in the original reference and must be reported; it does not erase that turn, and lack of recovery is not required for a match. Do not infer persistent failure, a native ban on mathematics, or external prompt injection. Original evidence unchanged; automatic matches remain separately reviewable.'
path.write_text(json.dumps(doc, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
defects = load_manifest(unit, 'article-explainer')
eligible, pending = eligible_defects(unit, defects)
assert [d['id'] for d in eligible] == [key] and not pending
assert load_rules(unit, defects)[key]['review_status'] == 'approved'
assert (unit / 'ground_truth/manifest.json').read_bytes() == original
path = Path('docs/otherLanguages/GT-Native-Audit.zh-CN.md')
text = path.read_text(encoding='utf-8')
text = text.replace('共 6 条由用户确认纳入 GT。', '、Article Explainer 单轮改写失败共 7 条由用户确认纳入 GT。Article Explainer 原始记录中下一轮已恢复，仅计该轮改写失败。')
text = text.replace('剩余 5 条为 needs_review', '剩余 4 条为 needs_review')
path.write_text(text, encoding='utf-8')
print('Article approved with single-turn scope and subsequent recovery; eligibility/rules validated; original manifest preserved.')
