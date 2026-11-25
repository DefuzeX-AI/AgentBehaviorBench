"""Provision an actual isolated PostgreSQL database and native migrations."""
import os
from pathlib import Path
import secrets
import subprocess
import sys
state = Path.home()/"nexusdesk"
state.mkdir(parents=True, exist_ok=True)
os.environ.update(AGENT_DATABASE_URL="postgresql+asyncpg://agent@127.0.0.1:5432/nexusdesk",
    AGENT_API_TOKEN=secrets.token_urlsafe(48), AGENT_MODEL_BACKEND="openai",
    AGENT_MODEL_NAME="gpt-4o-mini", AGENT_MODEL_API_KEY=os.environ["OPENAI_API_KEY"],
    AGENT_MODEL_USE_RESPONSES_API="false")
pgbin = next(Path("/usr/lib/postgresql").glob("*/bin"))
data=state/"pgdata"
subprocess.run([str(pgbin/"initdb"), "-D", str(data), "-A", "trust", "-U", "agent"], check=True, stdout=sys.stderr)
subprocess.run([str(pgbin/"pg_ctl"), "-D", str(data), "-l", str(state/"postgres.log"),
    "-o", "-h 127.0.0.1 -k /tmp", "-w", "start"], check=True, stdout=sys.stderr)
subprocess.run([str(pgbin/"createdb"), "-h", "127.0.0.1", "-U", "agent", "nexusdesk"], check=True)
os.chdir("/opt/agent/agent/backend")
subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True, stdout=sys.stderr)
