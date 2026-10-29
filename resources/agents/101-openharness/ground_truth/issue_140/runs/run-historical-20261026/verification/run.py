import os,sys,subprocess,json
from pathlib import Path
from dotenv import dotenv_values
R=Path(__file__).resolve().parent
config=dotenv_values(R.parents[1]/'.env');arm=sys.argv[1]
env=dict(os.environ)
model=config.get('ABB_MODEL') or config.get('DEEPSEEK_MODEL')
base=config.get('DEEPSEEK_BASE_URL') or 'https://api.deepseek.com/v1'
key=config.get('DEEPSEEK_API_KEY')
assert model and key, 'Missing configured DeepSeek model or credential'
env.update(ABB_AGENT_MODEL_API_KEY=key,ABB_AGENT_MODEL=model,ABB_AGENT_MODEL_BASE_URL=base)
image='v-oh140:baseline' if arm=='before' else 'v-oh140:after'
inspect=subprocess.check_output(['docker','image','inspect',image],text=True)
(R/f'{arm}-image.json').write_text(inspect)
image=json.loads(inspect)[0]['Id']
cmd=['docker','run','--rm','--name',f'v-oh140-{arm}','--cpus','2','--memory','3g','-e','ABB_AGENT_MODEL_API_KEY','-e','ABB_AGENT_MODEL','-e','ABB_AGENT_MODEL_BASE_URL','-v',f'{R}:/e',image,'python3','/e/driver.py',arm]
print(json.dumps({'arm':arm,'model':model,'base_url':base}),flush=True)
with (R/f'{arm}.log').open('w') as log:
    p=subprocess.Popen(cmd,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    for line in p.stdout:
        print(line,end='',flush=True);log.write(line);log.flush()
    code=p.wait()
raise SystemExit(code)
