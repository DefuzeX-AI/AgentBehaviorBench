"""Start the native graph server and authenticated BFF over a real local database."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import urllib.request

state = Path.home()/"chat-gun"
state.mkdir(parents=True, exist_ok=True)
pgbin = next(Path("/usr/lib/postgresql").glob("*/bin"))
data = state/"pgdata"
subprocess.run([str(pgbin/"initdb"), "-D", str(data), "-A", "trust", "-U", "agent"], check=True, stdout=sys.stderr)
subprocess.run([str(pgbin/"pg_ctl"), "-D", str(data), "-l", str(state/"postgres.log"),
                "-o", "-h 127.0.0.1 -k /tmp", "-w", "start"], check=True, stdout=sys.stderr)
subprocess.run([str(pgbin/"createdb"), "-h", "127.0.0.1", "-U", "agent", "chatgun"], check=True)
subprocess.Popen(["redis-server", "--bind", "127.0.0.1", "--port", "6379", "--dir", str(state)], stdout=sys.stderr, stderr=sys.stderr)
token = secrets.token_urlsafe(32)
os.environ.update(DATABASE_URL="postgresql://agent@127.0.0.1:5432/chatgun?sslmode=disable",
                  REDIS_URI="redis://127.0.0.1:6379", BFF_RATE_LIMIT_REDIS_URI="redis://127.0.0.1:6379",
                  LLM_PROVIDER="qwen", QWEN_BASE_URL="https://api.openai.com/v1",
                  QWEN_API_KEY=os.environ["OPENAI_API_KEY"], BFF_PORT="8787",
                  BFF_LANGGRAPH_API_URL="http://127.0.0.1:2024", BFF_REQUIRE_AUTH="true",
                  BFF_API_KEYS=token, ABB_CHATGUN_TOKEN=token)
for key in ["QWEN_CHAT_MODEL", "QWEN_RESEARCH_MODEL", "QWEN_VISION_MODEL", "QWEN_TOOL_MODEL",
            "DEFAULT_MODEL", "CHAT_MODEL", "MATH_MODEL", "MCP_AGENT_MODEL", "SHOPPING_ASSISTANT_MODEL"]:
    os.environ[key] = "gpt-4o-mini"
os.environ["BFF_API_KEY_PRINCIPALS_JSON"] = json.dumps({token: {
    "principalId": "abb-local-service", "principalType": "service", "tenantId": "abb-local",
    "roles": [], "scopes": [], "activeScope": {"scopeId": "abb-local-service", "scopeType": "principal"}}})
root = Path("/opt/agent/agent")
(root/"backend/.env").touch()
subprocess.run(["npm", "run", "migrations:up"], cwd=root/"backend", check=True, stdout=sys.stderr)
graph = subprocess.Popen(["npm", "run", "dev", "--", "--no-browser", "--host", "127.0.0.1"], cwd=root/"backend", stdout=sys.stderr, stderr=sys.stderr)
bff = subprocess.Popen(["node", "dist/server.js"], cwd=root/"bff", stdout=sys.stderr, stderr=sys.stderr)
for url, process in [("http://127.0.0.1:2024/ok", graph), ("http://127.0.0.1:8787/api/health", bff)]:
    deadline = time.monotonic()+180
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Native Chat-Gun service exited before readiness")
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    break
        except OSError:
            time.sleep(0.5)
    else:
        raise RuntimeError("Native Chat-Gun service readiness timed out")
