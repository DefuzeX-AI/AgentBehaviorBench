"""Provide native Kimi model configuration from the ABB runtime."""
import json
import os
from pathlib import Path
for name in ("ABB_AGENT_MODEL", "ABB_AGENT_MODEL_BASE_URL", "ABB_AGENT_MODEL_API_KEY"):
    if not os.environ.get(name):
        raise RuntimeError(f"Missing runtime setting: {name}")
home = Path.home() / ".kimi"
home.mkdir(mode=0o700, parents=True, exist_ok=True)
os.environ["KIMI_CODE_HOME"] = str(home)
quote = json.dumps
config = ('default_model = "abb"\n[providers.abb]\ntype = "openai"\n'
          'api_key_env = "ABB_AGENT_MODEL_API_KEY"\n'
          f'base_url = {quote(os.environ["ABB_AGENT_MODEL_BASE_URL"])}\n'
          '[models.abb]\nprovider = "abb"\n'
          f'model = {quote(os.environ["ABB_AGENT_MODEL"])}\n'
          'max_context_size = 32768\n')
(home / "config.toml").write_text(config, encoding="utf-8")
os.execvp("node", ["node", "/opt/agent/agent/apps/kimi-code/dist/main.mjs", "acp"])
