"""Container-local deployment settings for the unmodified DeerFlow client.

The upstream example supplies tools and middleware defaults. Only model transport,
local sandbox opt-in, skills location and writable state paths are deployment
choices. ABB intercepts the declared OpenAI protocol and selects the real model.
"""
import os
from pathlib import Path


def prepare_runtime_config():
    import yaml

    source = Path(__file__).resolve().parents[1] / 'agent'
    home = Path('/tmp/abb-deerflow-state')
    home.mkdir(parents=True, exist_ok=True)
    config = yaml.safe_load((source / 'config.example.yaml').read_text(encoding='utf-8'))
    config['models'] = [{
        'name': 'abb-model',
        'display_name': 'ABB runtime model',
        'use': 'langchain_openai:ChatOpenAI',
        'model': 'abb-runtime-selected',
        'base_url': 'https://api.openai.com/v1',
        'api_key': '$OPENAI_API_KEY',
        'supports_thinking': False,
    }]
    config['sandbox']['use'] = 'deerflow.sandbox.local:LocalSandboxProvider'
    config['sandbox']['allow_host_bash'] = True
    config['skills']['path'] = str(source / 'skills')
    config['database']['sqlite_dir'] = str(home / 'data')
    path = home / 'config.yaml'
    path.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding='utf-8')
    os.environ['DEER_FLOW_PROJECT_ROOT'] = str(source)
    os.environ['DEER_FLOW_HOME'] = str(home)
    os.environ['DEER_FLOW_CONFIG_PATH'] = str(path)
    return path
