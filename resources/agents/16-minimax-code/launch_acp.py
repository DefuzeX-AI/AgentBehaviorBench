"""Provision native BYOK settings in the private container, then exec native ACP.

The JSON document is valid YAML for the pinned upstream config parser. The model
credential is BBA's intercepted surrogate, never the host OpenRouter/SDK key.
No prompts, model calls, tool implementations or history are changed here.
"""
import json
import os
from pathlib import Path


def main():
    directory = Path(os.environ['MINIMAX_DATA_DIR'])
    directory.mkdir(parents=True, exist_ok=True)
    model = 'gpt-4.1'
    settings = {'defaultModel': 'custom_provider:abb/' + model,
                'custom_provider': {'abb': {
                    'name': 'BBA intercepted model', 'kind': 'custom', 'enabled': True,
                    'api': 'openai-completions',
                    'options': {'apiKey': os.environ['OPENAI_API_KEY'],
                                'baseURL': 'https://api.openai.com/v1', 'authMode': 'api-key'},
                    'models': {model: {'name': model}}}}}
    path = directory / 'config.yaml'
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(settings, stream)
    os.execvp('node', ['node', '/opt/agent/agent/dist/cli.js', 'acp'])


if __name__ == '__main__':
    main()
