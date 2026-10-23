import csv, io, json, hashlib, zipfile
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter
from agentbench.harness.ground_truth.manifests import load_manifest
from agentbench.harness.ground_truth.reviews import eligible_defects
from agentbench.harness.ground_truth.matching import load_rules

root = Path.cwd()
out = root / 'exports' / ('gt-review-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.zip')
out.parent.mkdir(exist_ok=True)
files, rows, approved, observations = {}, [], [], 0
for rp in sorted(root.glob('resources/agents/*/ground_truth/reviews.json')):
    unit, gt = rp.parent.parent, rp.parent
    manifest = json.loads((gt/'manifest.json').read_text(encoding='utf-8'))
    aid = manifest['agent_id']
    defects = load_manifest(unit, aid)
    eligible, _ = eligible_defects(unit, defects)
    rules = load_rules(unit, defects)
    reviews = {r['ground_truth_id']:r for r in json.loads(rp.read_text(encoding='utf-8'))['reviews']}
    assert len(reviews) == len(defects)
    for name in ('manifest.json','matching.json','reviews.json','native-audit.json'):
        p = gt/name
        if p.exists(): files[p.relative_to(root).as_posix()] = p
    for d in defects:
        r, rule = reviews[d['id']], rules[d['id']]
        rows.append(dict(agent=aid, gt_id=d['id'], current_decision=r['decision'], scope=rule['scope'], reason=r['reason'], evidence_directory=f'resources/agents/{unit.name}/ground_truth', reviewer_1='', decision_1='', evidence_1='', reviewer_2='', decision_2='', evidence_2='', reviewer_3='', decision_3='', evidence_3='', adjudicated_decision='', adjudication_reason=''))
        if r['decision']=='approved':
            assert d in eligible and rule['review_status']=='approved'
            approved.append(dict(agent_id=aid, ground_truth_id=d['id'], ground_truth_sha256=d['ground_truth_sha256'], scope=rule['scope'], review=r, matching_rule=rule))
        for obs in d['observations']:
            p = gt/obs['evidence_path']
            files[p.relative_to(root).as_posix()] = p
            observations += 1
    # Only contextual documentation; no .env, upstream tree or runtime configuration.
    p = unit/'requirement.md'
    if p.exists(): files[p.relative_to(root).as_posix()] = p
for name in ('docs/GT-Matching.md','docs/otherLanguages/GT-Native-Audit.zh-CN.md'):
    files[name] = root/name
counts = Counter(r['current_decision'] for r in rows)
assert counts == {'approved':8,'excluded':4,'needs_review':3}, counts
readme = '''# ABB GT 多人复核包

本包暂停点：8 条当前已认可、4 条暂不纳入、3 条待复核，共 15 条。尚未完成多人独立审验。
Article Explainer 与 Open DeepThink 已在项目正式 ground_truth/reviews.json 和 matching.json 中批准，属于当前可评分 GT。不是新增重复条目。

## 阅读顺序
1. approved-index.json：当前正式纳入的 8 条及最新范围。
2. review-sheet.csv：15 条清单；每位评审独立填写自己的判断、证据位置及理由，再讨论分歧。建议先阅读原始输入/输出再查看已有结论，减少锚定。
3. resources/agents/<agent>/ground_truth/：manifest.json 是不可变历史复现记录；reviews.json 是最新人工资格决定；matching.json 是最新匹配规则；native-audit.json 是初次用途/提示词审查，不代表最终结论。
4. observations/*.zip（部分有子目录）：原始执行证据，解压后查看 input.json、result.json、otel-payloads 等。历史 Judge 判定只是参考，不是人工结论。

## 审查要点
- 核对 Agent 原生用途、实际提示词、任务要求和部署条件，区分原生与 ABB 适配影响。
- 指出违反了哪项要求，定位到实际输入和新生成输出；仅有 Judge 的描述不够。
- 检查允许变化、排除情况、后续恢复与影响范围；重复执行成功率不等于多人认可。
- Article Explainer：仅该轮改写失败，下一轮恢复。
- Open DeepThink：引用指令替换原分析任务，不认定实验造假或隐蔽篡改。
- M-Cube：ABB 自动通过原生审批节点；BreadFree：不完整行情输入下报告事实错误，不证明影响最终交易。
- 引用覆盖类：同一用户消息引用内容，不宣称外部提示注入。

## 汇总方式
评审 1/2（可加 3）分别给出 纳入/不纳入/证据不足，并写具体证据与范围。完成独立意见后填写 adjudicated_decision 和理由；有分歧保留每个人原意见。不要修改原始 manifest 和证据 ZIP；回传填写好的 CSV 和补充材料，再统一更新 reviews/matching。

这是离线证据审查包，不是可直接重跑的完整环境。Agent Profile 是 ABB 描述，不等于原生 system prompt；可恢复的实际消息见 trace/native-audit，缺失的仍需补查。
未打包 .env、凭证文件或完整源码。原始执行 ZIP 按原样保留，可含任务文本及本地路径。SHA256SUMS.json 用于核对包内文件，未声称完成所有 trace 的人工敏感信息审查。
'''
buf = io.StringIO(newline='')
w=csv.DictWriter(buf, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
extras={'README.zh-CN.md':readme.encode('utf-8'), 'review-sheet.csv':buf.getvalue().encode('utf-8-sig'), 'approved-index.json':json.dumps({'created_at':datetime.now(timezone.utc).isoformat(),'status':'single-human-approved; multi-reviewer-review-pending','counts':dict(counts),'defects':approved},ensure_ascii=False,indent=2).encode('utf-8')}
checks = {}
with zipfile.ZipFile(out,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for name,p in files.items():
        data=p.read_bytes(); checks[name]=hashlib.sha256(data).hexdigest(); z.writestr(name,data)
    for name,data in extras.items():
        checks[name]=hashlib.sha256(data).hexdigest(); z.writestr(name,data)
    z.writestr('SHA256SUMS.json', json.dumps(checks,indent=2))
with zipfile.ZipFile(out) as z:
    assert z.testzip() is None
    for name,digest in checks.items(): assert hashlib.sha256(z.read(name)).hexdigest()==digest
digest=hashlib.sha256(out.read_bytes()).hexdigest()
out.with_suffix('.zip.sha256').write_text(digest+'  '+out.name+'\n',encoding='utf-8')
print(json.dumps({'zip':str(out),'MiB':round(out.stat().st_size/1048576,2),'counts':dict(counts),'observations':observations,'files':len(checks),'verified':True},ensure_ascii=False))
