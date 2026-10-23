import json,zipfile,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
for p in sorted((root/'resources/agents').glob('*/ground_truth/manifest.json')):
 d=json.loads(p.read_text(encoding='utf8'))
 if d['agent_id'] not in sys.argv[1:]: continue
 for gt in d['defects']:
  print('\nGT',gt['id'])
  with zipfile.ZipFile(p.parent/gt['observations'][0]['evidence_path']) as z:
   for n in z.namelist():
    if n.endswith('/input.json'): print(n,json.loads(z.read(n)).get('payload'))
    if n.endswith('/result.json'):
     v=json.loads(z.read(n)); raw=v.get('raw_output',{})
     if d['agent_id']=='breadfree-simu': v=raw
     elif d['agent_id']=='garmin-ai-coach': v={k:raw.get(k) for k in ('physiology_outputs','season_plan')}
     elif d['agent_id']=='m-cube': v={k:raw.get(k) for k in ('claims','approved_claims','claim_traceability')}
     elif d['agent_id']=='article-explainer':
      msgs=raw.get('messages',[]); v={'active_agent':raw.get('active_agent'),'last_message':msgs[-1:]}
     print(n,json.dumps(v,ensure_ascii=False)[:13500])
