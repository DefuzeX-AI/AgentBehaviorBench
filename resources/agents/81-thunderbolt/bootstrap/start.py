"""Configure and exec Thunderbolt's own ACP stdio coding agent."""
import json
import os
from pathlib import Path
for key in ("ABB_AGENT_MODEL", "ABB_AGENT_MODEL_BASE_URL", "ABB_AGENT_MODEL_API_KEY"):
    if not os.environ.get(key):
        raise RuntimeError(f"Missing runtime setting: {key}")
home = Path.home()/".thunderbolt"
home.mkdir(parents=True, exist_ok=True, mode=0o700)
path = home/"config.json"
# The native CLI migrates this supported legacy configuration into its current schema.
path.write_text(json.dumps({"provider": "openai-compat", "model": os.environ["ABB_AGENT_MODEL"],
    "baseUrl": os.environ["ABB_AGENT_MODEL_BASE_URL"], "apiKey": os.environ["ABB_AGENT_MODEL_API_KEY"]}), encoding="utf-8")
path.chmod(0o600)
os.execvp("bun", ["bun", "/opt/agent/agent/cli/src/index.ts", "acp", "serve"])
