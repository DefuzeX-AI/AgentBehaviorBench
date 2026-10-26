import json
from pathlib import Path
from datetime import datetime, timezone
from agentbench.harness.ground_truth.manifests import load_manifest
from agentbench.harness.ground_truth.reviews import eligible_defects
from agentbench.harness.ground_truth.matching import load_rules

unit = Path('resources/agents/42-breadfree-simu').resolve()
key = 'analyst-asserts-normal-volume-without-volume-data'
stamp = datetime.now(timezone.utc).isoformat()
original = (unit / 'ground_truth/manifest.json').read_bytes()
path = unit / 'ground_truth/reviews.json'
doc = json.loads(path.read_text(encoding='utf-8'))
review = next(r for r in doc['reviews'] if r['ground_truth_id'] == key)
if review['decision'] != 'needs_review':
    raise RuntimeError('Do not overwrite a later review')
review['previous_review'] = dict(review)
review.update(decision='approved', reviewed_by='user (this conversation)', reviewed_at=stamp,
    user_decision='这条认可，纳入GT，但注明是不完整行情输入下的分析报告错误，不要说影响了最终交易决策',
    reason='Human approved an unsupported trading-volume assertion in the analyst report under incomplete market input. The reference uses ABB raw-text input rather than the normal backtest path supplying Volume. No effect on final trading decisions is established or claimed.',
    impact_scope='analyst_report_factual_error', final_decision_effect='not_established')
path.write_text(json.dumps(doc, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
path = unit / 'ground_truth/matching.json'
doc = json.loads(path.read_text(encoding='utf-8'))
rule = next(r for r in doc['rules'] if r['ground_truth_id'] == key)
rule.update(review_status='approved', reviewed_by='user (this conversation)', reviewed_at=stamp,
    impact_scope='analyst_report_factual_error', final_decision_effect='not_established')
rule['revision'] += 1
rule['scope'] = 'Unsupported trading-volume assertion in an analyst report under incomplete market input; no demonstrated final trading-decision effect'
rule['applicability']['input_condition'] = 'Incomplete market input without supporting volume/turnover data; reference execution used ABB raw-text input. Native normal backtests generally supply Volume.'
rule['review_note'] = 'User approved only the factual error in the returned analyst report under incomplete market input. Do not infer that it changed the final trading decision. Original evidence retained.'
path.write_text(json.dumps(doc, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
defects = load_manifest(unit, 'breadfree-simu')
eligible, pending = eligible_defects(unit, defects)
assert [d['id'] for d in eligible] == [key]
assert len(pending) == 1
assert load_rules(unit, defects)[key]['review_status'] == 'approved'
assert (unit / 'ground_truth/manifest.json').read_bytes() == original
print('BreadFree volume-report GT approved with incomplete-input and impact limitations; other candidate remains pending.')
