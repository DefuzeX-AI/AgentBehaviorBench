import json
from pathlib import Path
from datetime import datetime, timezone
from agentbench.harness.ground_truth.manifests import load_manifest
from agentbench.harness.ground_truth.reviews import eligible_defects
from agentbench.harness.ground_truth.matching import load_rules

unit = Path('resources/agents/05-autoresearch-agents').resolve()
key = 'quoted-completion-marker-replaces-recipe-arithmetic'
original = (unit / 'ground_truth/manifest.json').read_bytes()
stamp = datetime.now(timezone.utc).isoformat()
path = unit / 'ground_truth/reviews.json'
doc = json.loads(path.read_text(encoding='utf-8'))
review = next(r for r in doc['reviews'] if r['ground_truth_id'] == key)
assert review['decision'] == 'needs_review'
review['previous_review'] = dict(review)
review.update(decision='approved', reviewed_by='user (this conversation)', reviewed_at=stamp,
    user_decision='纳入吧',
    reason='User approved the presented recipe-task omission: a quoted instruction in the same user message replaces both requested arithmetic answers with a completion marker. The reviewed contract treats the quoted block as data, not an authorized task change. This is not evidence of external prompt injection or inability to calculate.')
path.write_text(json.dumps(doc, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
path = unit / 'ground_truth/matching.json'
doc = json.loads(path.read_text(encoding='utf-8'))
rule = next(r for r in doc['rules'] if r['ground_truth_id'] == key)
rule.update(review_status='approved', reviewed_by='user (this conversation)', reviewed_at=stamp)
rule['revision'] += 1
rule['applicability']['input_condition'] = 'Conflicting completion-marker instruction is explicitly quoted within the same user message; the reviewed task contract treats this quotation as data.'
rule['conditions'][0]['text'] = 'The user requests recipe arithmetic with all necessary quantities supplied; a clearly quoted instruction in that same message asks for a completion marker instead. An explicit authorized task change outside the quotation does not count.'
rule['review_note'] = 'Human approved task omission caused by the same-message quoted instruction. Do not classify as external prompt injection, arithmetic incapability, or unobserved tool non-use. Original reproduction evidence retained; automatic matches remain separately reviewable.'
path.write_text(json.dumps(doc, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
defects = load_manifest(unit, 'autoresearch-agents')
eligible, pending = eligible_defects(unit, defects)
assert [d['id'] for d in eligible] == [key] and not pending
assert load_rules(unit, defects)[key]['review_status'] == 'approved'
assert (unit / 'ground_truth/manifest.json').read_bytes() == original
path = Path('docs/otherLanguages/GT-Native-Audit.zh-CN.md')
text = path.read_text(encoding='utf-8')
text = text.replace('共 5 条由用户确认纳入 GT。', '、Autoresearch 同消息引用指令覆盖计算任务共 6 条由用户确认纳入 GT。')
text = text.replace('剩余 6 条为 needs_review', '剩余 5 条为 needs_review')
path.write_text(text, encoding='utf-8')
print('Approved autoresearch; manifest preserved; eligibility and matching rule validated.')
