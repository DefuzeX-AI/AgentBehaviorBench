from pathlib import Path
import shutil, json
root = Path(__file__).resolve().parent
repo = root.parent.parent
original = repo / 'resources/agents/70-reasonix'
gt = json.loads((original / 'ground_truth/issue-14403/case.verified.json').read_text(encoding='utf-8'))
(root / 'gt-original.json').write_text(json.dumps(gt, indent=2, ensure_ascii=False), encoding='utf-8')
(root / 'case.json').write_text(json.dumps({'schema':'abb.cases.v1','cases':[{'case_id':gt['case_id'],'input_type':'text','inputs':[{'input_id':f'step-{i+1}','payload':p} for i,p in enumerate(gt['steps'])]}]},indent=2),encoding='utf-8')
registry = ['schema_version = "defuzex-bench.registry.v1"']
for arm in ['before','after']:
    unit = root / f'verify-reasonix14403-{arm}'
    unit.mkdir(exist_ok=True)
    for name in ['bootstrap','network']:
        shutil.copytree(original/name, unit/name, dirs_exist_ok=True)
    shutil.copy2(original/'requirement.md',unit/'requirement.md')
    shutil.copy2(original/'.dockerignore',unit/'.dockerignore')
    (unit/'agent').mkdir(exist_ok=True)
    (unit/'agent/provenance.json').write_text(json.dumps({'commit':gt['commit_version'],'arm':arm}),encoding='utf-8')
    (unit/'evaluation/fixture').mkdir(parents=True,exist_ok=True)
    (unit/'evaluation/fixture/settings.ini').write_bytes(b'[client]\r\nretries=3\r\nbackoff=2\r\n')
    manifest=(original/'agent.toml').read_text(encoding='utf-8').replace('agent_id = "reasonix"',f'agent_id = "{unit.name}"').replace('method = "install"','method = "bundled"').replace('2ddc6f646e71eafd415c7168fb7c800e43ee0ccf',gt['commit_version']).replace('initial_state = "empty"','initial_state = "fixture"\nfixture = "evaluation/fixture"')
    (unit/'agent.toml').write_text(manifest,encoding='utf-8')
    (unit/'Dockerfile').write_text('''FROM defuzex-agentbench/verify259-before:f06d57ad38fe4340be473911a162798e22d5d0df18d4485baed3db4bee53cdcd
USER root
COPY agent/reasonix /opt/reasonix/bin/reasonix
RUN chmod 0755 /opt/reasonix/bin/reasonix
COPY .abb-runtime/ /opt/abb-runtime/
COPY bootstrap/ /opt/agent/bootstrap/
COPY network/ /opt/agent/network/
COPY agent.toml /opt/agent/agent.toml
COPY evaluation/ /opt/agent/evaluation/
USER agent
''',encoding='utf-8')
    registry.append(f'\n[[agents]]\nagent_id = "{unit.name}"\npath = "{unit.as_posix()}"\nenabled = true\nstatus = "ready"\nframework = "acp"\ncase = 1\nstep = 1\n')
(root/'registry.toml').write_text('\n'.join(registry),encoding='utf-8')
