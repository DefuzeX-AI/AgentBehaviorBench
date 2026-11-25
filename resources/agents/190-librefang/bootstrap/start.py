"""Configure the native default model and start LibreFang's own ACP kernel."""
import os
from pathlib import Path
import tomllib
import tomli_w

home = Path(os.environ.get('LIBREFANG_HOME') or Path.home()/'.librefang')
home.mkdir(parents=True, exist_ok=True)
os.environ.setdefault('LIBREFANG_HOME', str(home))
config = Path(os.environ.get('LIBREFANG_CONFIG_PATH') or home/'config.toml')
data = tomllib.loads(config.read_text()) if config.exists() else {}
data['default_model'] = {
    **data.get('default_model', {}),
    'provider': 'openai', 'model': os.environ['ABB_AGENT_MODEL'],
    'api_key_env': 'ABB_AGENT_MODEL_API_KEY',
    'base_url': os.environ['ABB_AGENT_MODEL_BASE_URL'],
}
config.write_text(tomli_w.dumps(data), encoding='utf8')
config.chmod(0o600)
os.execvp('librefang', ['librefang', 'acp'])
