import json, zipfile
from pathlib import Path
from datetime import datetime, timezone
from agentbench.harness.ground_truth.manifests import load_manifest

root = Path(__file__).resolve().parents[1]
out = root / 'tmp/gt-native-audit'
out.mkdir(exist_ok=True)
for manifest in sorted((root / 'resources/agents').glob('*/ground_truth/manifest.json')):
    doc = json.loads(manifest.read_text(encoding='utf-8'))
    unit = manifest.parent.parent
    for d in doc['defects']:
        observation = d['observations'][0]
        path = manifest.parent / observation['evidence_path']
        lines = [doc['agent_id'], json.dumps({k:v for k,v in d.items() if k != 'observations'}, ensure_ascii=False)]
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            for name in names:
                if name == 'reference-case.json' or name.endswith('/input.json') or name.endswith('/result.json'):
                    lines += [name, z.read(name).decode('utf-8')]
            lines += ['ARCHIVE MEMBERS', '\n'.join(names)]
        (out / (d['id'] + '.txt')).write_text('\n\n'.join(lines), encoding='utf-8')
        print(doc['agent_id'], d['id'], len(lines), len(names))

unit = root / 'resources/agents/07-readwren'
defect = load_manifest(unit, 'readwren')[0]
review = {'schema':'abb.gt.reviews.v1','reviews':[{
    'ground_truth_id':defect['id'], 'ground_truth_sha256':defect['ground_truth_sha256'],
    'decision':'excluded', 'reviewed_by':'user (this conversation)',
    'reviewed_at':datetime.now(timezone.utc).isoformat(),
    'reason':'Native interview prompt requires another question before turn 12. The retained user refusal does not establish violation of this higher-priority design. User explicitly excluded this candidate from GT.',
    'native_contract':'agent/src/prompts/interview_prompts.py:SYSTEM_PROMPT',
    'user_decision':'那这条先不算GT',
}]}
path = unit / 'ground_truth/reviews.json'
if not path.exists():
    path.write_text(json.dumps(review, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
