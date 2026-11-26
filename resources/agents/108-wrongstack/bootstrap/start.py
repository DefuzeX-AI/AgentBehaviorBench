"""Run WrongStack's full native ACP engine with deployment-only model settings."""
import os
import json
from pathlib import Path

os.environ.update(
    WRONGSTACK_PROVIDER='abb',
    WRONGSTACK_MODEL=os.environ['ABB_AGENT_MODEL'],
    WRONGSTACK_API_KEY=os.environ['ABB_AGENT_MODEL_API_KEY'],
    WRONGSTACK_BASE_URL=os.environ['ABB_AGENT_MODEL_BASE_URL'],
)
config = Path.home()/'.wrongstack/profiles/default/config.json'
config.parent.mkdir(parents=True, exist_ok=True)
config.write_text(json.dumps({
    'provider': 'abb', 'model': os.environ['ABB_AGENT_MODEL'],
    'providers': {'abb': {
        'family': 'openai-compatible',
        'baseUrl': os.environ['ABB_AGENT_MODEL_BASE_URL'],
        'envVars': ['ABB_AGENT_MODEL_API_KEY'],
        'models': [os.environ['ABB_AGENT_MODEL']],
    }},
}), encoding='utf8')
config.chmod(0o600)
os.execvp('bun', ['bun', '/opt/agent/agent/packages/cli/dist/index.js', 'acp'])
