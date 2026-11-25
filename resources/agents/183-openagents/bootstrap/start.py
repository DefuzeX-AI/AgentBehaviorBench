"""Run Coder's native ACP server and Microcoder engine with intercepted model credentials."""
import os

if os.environ['ABB_AGENT_MODEL_PROVIDER'] != 'openrouter' or os.environ['ABB_AGENT_MODEL_BASE_URL'].rstrip('/') != 'https://openrouter.ai/api/v1':
    raise RuntimeError('Native Microcoder requires the standard OpenRouter Chat Completions URL')

os.environ["OPENROUTER_API_KEY"] = os.environ["ABB_AGENT_MODEL_API_KEY"]
os.execv("/bin/bash", ["bash", "/opt/agent/agent/coder/tui/coder.sh", "acp", "--engine", "microcoder"])
