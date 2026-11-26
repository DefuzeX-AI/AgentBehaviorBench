"""Deploy native services, authenticate, and call REDCELL's original draft chat API."""
import asyncio
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, '/opt/agent/agent/apps/api')

request = json.loads(Path(sys.argv[1]).read_text())
work = Path(request['workspace'])
password = secrets.token_urlsafe(24)
os.environ.update(
    REDCELL_DATABASE_URL='postgresql+asyncpg://agent@127.0.0.1:5432/redcell',
    REDCELL_REDIS_URL='redis://127.0.0.1:6379/0',
    REDCELL_S3_ENDPOINT='http://127.0.0.1:8333',
    REDCELL_ADMIN_USERNAME='abb-operator', REDCELL_ADMIN_PASSWORD=password,
    REDCELL_RUN_MODE='live',
)
processes = []
streams = []
def start(args, name):
    stream = (work/(name+'.log')).open('w')
    streams.append(stream)
    proc = subprocess.Popen(args, stdout=stream, stderr=subprocess.STDOUT)
    processes.append(proc)
    return proc

async def chat():
    import httpx
    from redcell_core.seed import bootstrap
    from app.main import app
    await bootstrap()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://localhost') as client:
            response = await client.post('/api/v1/auth/login', json={'username':'abb-operator','password':password})
            response.raise_for_status()
            response = await client.post('/api/v1/provider-keys', json={
                'providerId':'custom', 'apiKey':os.environ['ABB_AGENT_MODEL_API_KEY'],
                'apiBase':os.environ['ABB_AGENT_MODEL_BASE_URL'],
            })
            response.raise_for_status()
            response = await client.post('/api/v1/sessions/draft/chat', json={
                'messages':[{'role':'user','content':request['text']}],
                'provider':'custom','model':os.environ['ABB_AGENT_MODEL'],
            })
            response.raise_for_status()
            result = response.json()
            if result['reply'].startswith(('Model call failed:', 'No API key is set')):
                raise RuntimeError(result['reply'])
            return {'native_mode':'session_draft_chat', 'response':result, 'engagement_started':False}

try:
    pg = work/'postgres'
    subprocess.run(['/usr/lib/postgresql/15/bin/initdb','-D',str(pg),'-A','trust','-U','agent'], check=True, stdout=sys.stderr)
    start(['/usr/lib/postgresql/15/bin/postgres','-D',str(pg),'-h','127.0.0.1','-k',str(work),'-c','shared_buffers=32MB','-c','max_connections=20'], 'postgres')
    for _ in range(100):
        if subprocess.run(['/usr/lib/postgresql/15/bin/pg_isready','-h','127.0.0.1'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode==0:
            break
        time.sleep(.2)
    else:
        raise RuntimeError('Native PostgreSQL deployment did not start')
    subprocess.run(['/usr/lib/postgresql/15/bin/createdb','-h','127.0.0.1','-U','agent','redcell'], check=True)
    start(['redis-server','--bind','127.0.0.1','--save','','--appendonly','no'], 'redis')
    data = work/'objects'
    data.mkdir()
    storage = start(['weed','server','-ip=127.0.0.1','-ip.bind=127.0.0.1','-s3','-s3.config=/opt/agent/agent/docker/seaweedfs/s3.dev.json','-dir='+str(data),'-volume.max=1','-volume.port=8081'], 'storage')
    for _ in range(450):
        if storage.poll() is not None:
            raise RuntimeError(f'Native SeaweedFS exited with status {storage.returncode}')
        try:
            with urllib.request.urlopen('http://127.0.0.1:8333/healthz',timeout=1) as response:
                if response.status == 200:
                    break
        except OSError:
            time.sleep(.2)
    else:
        raise RuntimeError('Native SeaweedFS deployment did not start')
    subprocess.run(['alembic','upgrade','head'], cwd='/opt/agent/agent/packages/core',check=True)
    result = asyncio.run(chat())
    Path(sys.argv[2]).write_text(json.dumps(result,ensure_ascii=False))
except Exception:
    for name in ('postgres', 'redis', 'storage'):
        path = work/(name+'.log')
        if path.exists():
            diagnostic = path.read_text(errors='replace')[-5000:]
            for secret in (password, os.environ['ABB_AGENT_MODEL_API_KEY']):
                diagnostic = diagnostic.replace(secret, '[REDACTED]')
            print(f'Native {name} service diagnostic:\n{diagnostic}', file=sys.stderr)
    raise
finally:
    for proc in reversed(processes):
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
    for stream in streams:
        stream.close()
