"""Select the model through DotCraft's native user configuration, then start ACP."""
import json
import os
import subprocess
import sys
from pathlib import Path

config = Path.home()/'.craft/config.json'
config.parent.mkdir(parents=True, exist_ok=True)
config.write_text(json.dumps({
    'ProviderId': 'abb',
    'Providers': {'abb': {
        'DisplayName': 'ABB model', 'AuthMethod': 'apiKey',
        'Protocol': 'openai-chat-completions',
        'ApiKey': '$ABB_AGENT_MODEL_API_KEY',
        'EndPoint': os.environ['ABB_AGENT_MODEL_BASE_URL']}},
    'ProviderPreferences': {'abb': {'model': os.environ['ABB_AGENT_MODEL']}}
}), encoding='utf8')
config.chmod(0o600)
subprocess.run(
    ['dotcraft', 'setup', '--provider-mode', 'existing', '--provider-id', 'abb',
     '--model', os.environ['ABB_AGENT_MODEL']],
    check=True, stdout=sys.stderr,
)
os.execvp('dotcraft', ['dotcraft', 'acp'])
