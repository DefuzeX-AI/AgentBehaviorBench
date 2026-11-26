"""Configure the bundled native OpenTeams CLI and exec its ACP command."""
import json
import os
from pathlib import Path

for key in ('ABB_AGENT_MODEL', 'ABB_AGENT_MODEL_BASE_URL', 'ABB_AGENT_MODEL_API_KEY'):
    if not os.environ.get(key):
        raise RuntimeError(f'Missing runtime setting: {key}')
model = os.environ['ABB_AGENT_MODEL']
directory = Path.home()/'.config/openteams-cli'
directory.mkdir(parents=True, exist_ok=True)
path = directory/'openteams.json'
path.write_text(json.dumps({
    'model': f'abb/{model}',
    'provider': {'abb': {
        'npm': '@ai-sdk/openai-compatible', 'name': 'ABB runtime model',
        'options': {'baseURL': os.environ['ABB_AGENT_MODEL_BASE_URL'],
                    'apiKey': os.environ['ABB_AGENT_MODEL_API_KEY']},
        'models': {model: {'name': model,
            # Conservative deployment budgets, not claimed provider maximums.
            'limit': {'context': 32768, 'output': 4096}}},
    }},
}), encoding='utf8')
path.chmod(0o600)
os.environ['OPENTEAMS_CONFIG'] = str(path)
os.environ['OPENTEAMS_DISABLE_AUTOUPDATE'] = '1'
os.environ['OPENTEAMS_DISABLE_MODELS_FETCH'] = '1'
os.chdir('/opt/agent/agent/openteams-cli/packages/openteams-cli')
os.execvp('bun', ['bun', 'run', '--conditions=browser',
    '/opt/agent/agent/openteams-cli/packages/openteams-cli/src/index.ts', 'acp', '--cwd', '/workspace'])
