import json,hashlib
from pathlib import Path
from dotenv import dotenv_values
R=Path(__file__).resolve().parent
env=dotenv_values(R.parents[1]/'.env');secret=env.get('DEEPSEEK_API_KEY','').encode();assert len(secret)>8
hits=[]
for p in R.rglob('*'):
 if p.is_file() and secret in p.read_bytes():hits.append(str(p.relative_to(R)))
assert not hits, 'Credential material found in artifacts'
checks=json.loads((R/'artifact-checks.json').read_text(encoding='utf-8'))
checks['credential_scan_no_matches']=True
before=json.loads((R/'before-image-probe.json').read_text());after=json.loads((R/'after-image-probe.json').read_text())
assert not before['missing_original_files'] and not before['changed_original_files']
assert not after['missing_original_files'] and [x['file'] for x in after['changed_original_files']]==['src/query/index.ts']
assert before['dist_main_sha256']==after['dist_main_sha256']
checks['all_runtime_source_files_verified']=True;checks['compiled_session_identical']=True
(R/'artifact-checks.json').write_text(json.dumps(checks,indent=2)+'\n',encoding='utf-8')
files=[]
for p in sorted(R.rglob('*')):
 if p.is_file() and p.name!='evidence-index.json':
  data=p.read_bytes();files.append({'path':p.relative_to(R).as_posix(),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
index={'hash_algorithm':'SHA-256','root':str(R),'excludes':['evidence-index.json (self)'],'files':files}
(R/'evidence-index.json').write_text(json.dumps(index,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'indexed_files':len(files),'checks':checks}))
