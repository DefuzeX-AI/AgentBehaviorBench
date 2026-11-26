"""Provision the native local fount service and launch its own ACP stdio client."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

import httpx

root = Path('/opt/agent/agent')
for key in ('ABB_AGENT_MODEL', 'ABB_AGENT_MODEL_BASE_URL', 'ABB_AGENT_MODEL_API_KEY'):
    if not os.environ.get(key):
        raise RuntimeError(f'Missing runtime setting: {key}')
os.environ['OPENAI_API_KEY'] = os.environ['ABB_AGENT_MODEL_API_KEY']
os.environ['OPENAI_MODEL'] = os.environ['ABB_AGENT_MODEL']
os.environ['OPENAI_BASE_URL'] = os.environ['ABB_AGENT_MODEL_BASE_URL'].rstrip('/') + '/chat/completions'
os.environ['FOUNT_URL'] = 'http://localhost:8931'
os.environ['FOUNT_CHAR'] = 'ZL-31'
config = json.loads((root/'default/config.json').read_text())
config['listen'] = '127.0.0.1'
(root/'data/config.json').write_text(json.dumps(config))
server = subprocess.Popen(['deno', 'run', '-A', 'src/server/index.mjs'],
                          cwd=root, stdout=sys.stderr, stderr=sys.stderr)
try:
    with httpx.Client(base_url=os.environ['FOUNT_URL'], trust_env=False, timeout=180) as client:
        for _ in range(180):
            if server.poll() is not None:
                raise RuntimeError(f'Native fount server exited: {server.returncode}')
            try:
                if client.get('/api/getavailablelocales').is_success:
                    break
            except httpx.TransportError:
                pass
            time.sleep(1)
        else:
            raise RuntimeError('Native fount server did not become ready')
        identity = {'username': 'abb-native', 'password': secrets.token_urlsafe(32)}
        client.post('/api/register', json=identity).raise_for_status()
        client.post('/api/login', json={**identity, 'deviceid': 'abb-local'}).raise_for_status()
        response = client.post('/api/apikey/create', json={'description': 'Local ACP session'})
        response.raise_for_status()
        os.environ['FOUNT_API_KEY'] = response.json()['apiKey']
        client.headers['Authorization'] = 'Bearer ' + os.environ['FOUNT_API_KEY']
        response = client.get('/api/parts/shells:serviceSourceManage/AI/generators/proxy/template')
        response.raise_for_status()
        model_config = response.json()
        model_config.update(url=os.environ['OPENAI_BASE_URL'], model=os.environ['OPENAI_MODEL'],
                            apikey=os.environ['OPENAI_API_KEY'])
        client.post('/api/parts/shells:serviceSourceManage/AI/abb-model',
                    json={'generator': 'proxy', 'config': model_config}).raise_for_status()
        client.post('/api/defaultpart/add',
                    json={'parent': 'serviceSources/AI', 'child': 'abb-model'}).raise_for_status()
    # This is the upstream stdio-to-WebSocket ACP client, not an alternative agent loop.
    result = subprocess.run(['deno', 'run', '--allow-env', '--allow-net',
        'src/public/parts/shells/ideIntegration/public/fount_ide_agent.mjs'], cwd=root)
    sys.exit(result.returncode)
finally:
    if server.poll() is None:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()
