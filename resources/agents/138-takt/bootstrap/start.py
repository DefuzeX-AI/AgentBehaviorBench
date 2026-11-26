"""Configure TAKT's native OpenCode provider and run its own ACP server."""
import json
import os
from pathlib import Path

model = os.environ["ABB_AGENT_MODEL"]
state = Path.home()/".takt"
state.mkdir(parents=True, exist_ok=True)
(state/"config.yaml").write_text("language: en\nprovider: opencode\nmodel: " + json.dumps("abb/" + model) + "\n")
provider = Path.home()/".config/opencode"
provider.mkdir(parents=True, exist_ok=True)
path = provider/"opencode.json"
path.write_text(json.dumps({"provider": {"abb": {
    "npm": "@ai-sdk/openai-compatible", "name": "ABB runtime model",
    "options": {"baseURL": os.environ["ABB_AGENT_MODEL_BASE_URL"],
                "apiKey": os.environ["ABB_AGENT_MODEL_API_KEY"]},
    "models": {model: {"name": model,
        "limit": {"context": 32768, "output": 4096}}},
}}}))
path.chmod(0o600)
os.environ["TAKT_OPENCODE_VERSION"] = "v1"
os.environ["OPENCODE_CONFIG"] = str(path)
os.execvp("node", ["node", "/opt/agent/agent/dist/app/acp/index.js"])
