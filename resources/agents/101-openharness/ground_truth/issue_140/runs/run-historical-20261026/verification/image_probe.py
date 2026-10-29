import json,hashlib,subprocess,sys
from pathlib import Path
R=Path('/e');arm=sys.argv[1];p=json.loads((R/'provenance.json').read_text());root=Path('/opt/agent/agent');changed=[];missing=[]
for rel,expected in p['files'].items():
 f=root/rel
 if not f.exists():missing.append(rel);continue
 actual=hashlib.sha256(f.read_bytes()).hexdigest()
 if actual!=expected['sha256']:changed.append({'file':rel,'sha256':actual})
result={'arm':arm,'missing_original_files':missing,'changed_original_files':changed,'package_version':json.loads((root/'package.json').read_text())['version'],'node':subprocess.check_output(['node','--version'],text=True).strip(),'dist_main_sha256':hashlib.sha256((root/'dist/main.js').read_bytes()).hexdigest(),'dist_query_sha256':hashlib.sha256((root/'dist/query/index.js').read_bytes()).hexdigest()}
(R/f'{arm}-image-probe.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
