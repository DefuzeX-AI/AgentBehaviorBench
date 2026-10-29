import hashlib,json,urllib.request,zipfile,io
from pathlib import Path
R=Path(__file__).resolve().parent
U=R.parents[1]/'resources/agents/101-openharness'
rev='2a7b7b8e1c0b132241d0eebb906dc86863ca19d8'
url=f'https://codeload.github.com/zhijiewong/openharness/zip/{rev}'
raw=urllib.request.urlopen(url,timeout=120).read()
(R/'upstream.zip').write_bytes(raw)
z=zipfile.ZipFile(io.BytesIO(raw)); prefix=z.namelist()[0]
files={}
for n in z.namelist():
    if n.endswith('/'):continue
    rel=n[len(prefix):];data=z.read(n);p=R/'src'/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    local=U/'agent'/rel
    files[rel]={'sha256':hashlib.sha256(data).hexdigest(),'local_matches':local.exists() and local.read_bytes()==data}
state=json.loads((R.parents[1]/'cache/sources/47daedf8e996be746c087cce32da771a038abd863220c428ece92e234777565c.state.json').read_text())
(R/'provenance.json').write_text(json.dumps({'repository':'zhijiewong/openharness','revision':rev,'url':url,'archive_sha256':hashlib.sha256(raw).hexdigest(),'files':files,'cache_manifest_matches':all(state['files'].get(k)==v['sha256'] for k,v in files.items()),'mismatches':[k for k,v in files.items() if not v['local_matches']]},indent=2))
for n in ['agent.toml','source-manifest.json','Dockerfile','README.md']:
    (R/('original-'+n)).write_bytes((U/n).read_bytes())
(R/'bootstrap').mkdir(exist_ok=True)
for p in (U/'bootstrap').iterdir():
    if p.is_file():(R/'bootstrap'/p.name).write_bytes(p.read_bytes())
print(json.dumps({'files':len(files),'local_mismatches':[k for k,v in files.items() if not v['local_matches']],'cache_manifest_matches':all(state['files'].get(k)==v['sha256'] for k,v in files.items())}))
