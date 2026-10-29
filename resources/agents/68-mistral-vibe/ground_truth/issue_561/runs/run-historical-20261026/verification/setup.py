import json, shutil
from pathlib import Path
r=Path('tmp/verify-issue561-20261026-parallel').resolve()
s=Path('tmp/verify-issue259-20261026/verify259-before')
gt=json.loads(Path('resources/agents/68-mistral-vibe/ground_truth/issue-561/case.verified.json').read_text())
(r/'gt-original.json').write_text(json.dumps(gt,indent=2))
(r/'case.json').write_text(json.dumps({'schema':'abb.cases.v1','cases':[{'case_id':gt['case_id'],'input_type':'text','inputs':[{'input_id':f'step-{i+1}','payload':p} for i,p in enumerate(gt['steps'])]}]},indent=2))
registry='schema_version = "defuzex-bench.registry.v1"\n'
for arm in ['before','after']:
 u=r/f'verify561-{arm}'; u.mkdir(exist_ok=True)
 for name in ['bootstrap','network']:
  shutil.copytree(s/name,u/name,dirs_exist_ok=True)
 for name in ['.dockerignore','requirement.md']:
  shutil.copy2(s/name,u/name)
 (u/'agent').mkdir(exist_ok=True)
 (u/'agent/provenance.txt').write_text('Historical source is installed in the base image; verified against pinned archive f71bfd3b8cdddbb4369c843da9c48d5f6c637ef7.\n')
 (u/'agent.toml').write_text((s/'agent.toml').read_text().replace('verify259-before',f'verify561-{arm}').replace('79f215d91cf8ca7c8970d9d81470b76199fecc43',gt['commit_version']))
 docker='FROM defuzex-agentbench/mistral-561-before:80557a6911f34c3249c271ddb9a64666f7d914bba906aecf8e4785f507648e16\nCOPY .abb-runtime/ /opt/abb-runtime/\nCOPY bootstrap/ /opt/agent/bootstrap/\nCOPY network/ /opt/agent/network/\nCOPY agent.toml /opt/agent/agent.toml\n'
 if arm=='after': docker+='USER root\nCOPY system_prompt.py /opt/vibe135/lib/python3.13/site-packages/vibe/core/system_prompt.py\n'
 (u/'Dockerfile').write_text(docker+'USER agent\n')
 registry+=f'\n[[agents]]\nagent_id = "verify561-{arm}"\npath = "{u.as_posix()}"\nenabled = true\nstatus = "ready"\nframework = "acp"\ncase = 1\nstep = 1\n'
(r/'registry.toml').write_text(registry)
