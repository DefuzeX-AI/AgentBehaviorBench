import asyncio,json,os,sys,tempfile,hashlib,shutil,time,subprocess
from pathlib import Path
sys.path.insert(0,'/opt/agent/bootstrap')
from launch import prepare
R=Path('/e');arm=sys.argv[1];out=R/arm;out.mkdir(exist_ok=True)
tempfile.tempdir=str(out)
async def main():
    runtime=out/'runtime';runtime.mkdir(exist_ok=True)
    for rel in ['dist/query/index.js','dist/main.js','dist/query/index.js.map','dist/main.js.map','src/query/index.ts','src/main.tsx','package-lock.json','package.json']:
        target=runtime/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(Path('/opt/agent/agent')/rel,target)
    deps=subprocess.run(['npm','ls','--json'],cwd='/opt/agent/agent',capture_output=True)
    (runtime/'npm-ls.json').write_bytes(deps.stdout)
    steps=json.loads((R/'case.original.json').read_text())['steps']
    command,env=prepare(dict(os.environ))
    command += ['--permission-mode','trust']
    command[2]='/e/observe.mjs'
    env['OH140_OUT']=str(out);env['NODE_V8_COVERAGE']=str(out/'coverage')
    meta={'arm':arm,'model':env['ABB_AGENT_MODEL'],'provider':'deepseek','base_url':env['ABB_AGENT_MODEL_BASE_URL'],'command':command,'home':env['HOME'],'steps':steps,'initial_workspace':list(Path('/w').iterdir()),'node':subprocess.check_output(['node','--version'],text=True).strip(),'uid':os.getuid()}
    meta['initial_workspace']=[str(p) for p in meta['initial_workspace']]
    (out/'meta.json').write_text(json.dumps(meta,indent=2))
    err=(out/'stderr.txt').open('wb');events=(out/'events.jsonl').open('wb')
    p=await asyncio.create_subprocess_exec(*command,cwd='/w',env=env,stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=err,limit=16*1024*1024)
    async def read():
        line=await asyncio.wait_for(p.stdout.readline(),600)
        if not line:raise RuntimeError('native process EOF')
        events.write(line);events.flush()
        return json.loads(line)
    ready=await read();assert ready['type']=='ready'
    sid=ready['sessionId'];print(arm,'ready',sid,flush=True)
    for i,prompt in enumerate(steps,1):
        p.stdin.write((json.dumps({'id':str(i),'prompt':prompt})+'\n').encode());await p.stdin.drain()
        while True:
            ev=await read()
            if ev['type'] in ('tool_end','error','turn_complete','turnStop'):print(arm,i,ev['type'],str(ev.get('message',ev.get('reason',ev.get('tool',''))))[:250],flush=True)
            if ev['type']=='turnStop' or (ev['type']=='error' and str(ev.get('message','')).startswith('No response received.')):break
        session=Path(env['HOME'])/'.oh/sessions'/f'{sid}.json'
        for _ in range(100):
            await asyncio.sleep(.05)
            if session.exists():
                s=json.loads(session.read_text())
                if sum(m.get('role')=='user' for m in s['messages'])==i:break
        shutil.copy2(session,out/f'state-{i}.json')
        dest=out/f'files-{i}';dest.mkdir(exist_ok=True)
        for f in Path('/w').rglob('*'):
            if f.is_file():
                target=dest/f.relative_to('/w');target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,target)
    p.stdin.write(b'{"command":"exit"}\n');await p.stdin.drain();p.stdin.close()
    await asyncio.wait_for(p.wait(),30);events.close();err.close()
    (out/'exit.json').write_text(json.dumps({'returncode':p.returncode}))
asyncio.run(main())
