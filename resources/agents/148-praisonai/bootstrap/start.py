"""Configure the native ACP server from ABB-owned model selection."""
import os
for name in ("ABB_AGENT_MODEL", "ABB_AGENT_MODEL_BASE_URL", "ABB_AGENT_MODEL_API_KEY"):
    if not os.environ.get(name):
        raise RuntimeError(f"Missing runtime setting: {name}")
os.environ["OPENAI_API_KEY"] = os.environ["ABB_AGENT_MODEL_API_KEY"]
os.environ["OPENAI_BASE_URL"] = os.environ["ABB_AGENT_MODEL_BASE_URL"]
from praisonai.acp import serve
serve(workspace="/workspace", model="openai/" + os.environ["ABB_AGENT_MODEL"])
