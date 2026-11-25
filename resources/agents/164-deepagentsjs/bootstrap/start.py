"""Configure only the model endpoint, then execute the native ACP CLI."""
import os

os.environ["OPENAI_API_KEY"] = os.environ["ABB_AGENT_MODEL_API_KEY"]
os.environ["OPENAI_BASE_URL"] = os.environ["ABB_AGENT_MODEL_BASE_URL"]
os.execvp("node", ["node", "/opt/agent/agent/libs/acp/dist/cli.js",
    "--model", "openai:" + os.environ["ABB_AGENT_MODEL"], "--workspace", "/workspace"])
