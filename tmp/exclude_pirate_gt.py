import json
from pathlib import Path
from datetime import datetime, timezone
from agentbench.harness.ground_truth.manifests import load_manifest
from agentbench.harness.ground_truth.reviews import eligible_defects
from agentbench.harness.ground_truth.matching import load_rules

unit = Path('resources/agents/08-langchain-streamlit-template').resolve()
stamp = datetime.now(timezone.utc).isoformat()
original = (unit / 'ground_truth/manifest.json').read_bytes()
path = unit / 'ground_truth/reviews.json'
doc = json.loads(path.read_text(encoding='utf-8'))
review = doc['reviews'][0]
if review['decision'] != 'needs_review':
    raise RuntimeError('Do not overwrite a later review')
review['previous_review'] = dict(review)
review.update(decision='excluded', reviewed_by='user (this conversation)', reviewed_at=stamp,
    user_decision='这条也先不算GT，角色口吻偏离影响太小，保留线索，继续下一条。',
    reason='User excluded this candidate for now because persona/tone deviation has insufficient practical impact for the current GT set. Preserve the evidence as a lead; do not infer mathematical failure or a security vulnerability.',
    follow_up='Retain persona deviation as a lead only; any substantive task failure requires separate evidence and human review.')
path.write_text(json.dumps(doc, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
path = unit / 'ground_truth/matching.json'
doc = json.loads(path.read_text(encoding='utf-8'))
doc['rules'][0].update(review_status='excluded', reviewed_by='user (this conversation)', reviewed_at=stamp,
    review_note='User excluded for now due to low impact of tone/persona deviation. Original observations retained as leads; not eligible for scoring.')
path.write_text(json.dumps(doc, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
defects = load_manifest(unit, 'langchain-streamlit-template')
assert eligible_defects(unit, defects)[0] == []
assert load_rules(unit, defects)[defects[0]['id']]['review_status'] == 'excluded'
assert (unit / 'ground_truth/manifest.json').read_bytes() == original
path = Path('docs/otherLanguages/GT-Native-Audit.zh-CN.md')
text = path.read_text(encoding='utf-8')
old = 'ReadWren、Garmin 默认测量日期、BreadFree 中间报告标记污染共 3 条排除（后两者暂不计入、保留调查线索）；剩余 7 条为 needs_review'
new = 'ReadWren、Garmin 默认测量日期、BreadFree 中间报告标记污染、Streamlit 海盗口吻偏离共 4 条排除（后三者暂不计入、保留调查线索）；剩余 6 条为 needs_review'
assert old in text
path.write_text(text.replace(old, new), encoding='utf-8')
print('Persona candidate excluded; evidence preserved; 5 approved, 4 excluded, 6 pending.')
