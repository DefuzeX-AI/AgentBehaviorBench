"""Provision an actual isolated PostgreSQL database and native migrations."""
import os
from pathlib import Path
import secrets
import subprocess
import sys
state = Path.home()/"optimizer"
state.mkdir(parents=True, exist_ok=True)
os.environ.update(DATABASE_URL="postgresql+psycopg://agent@127.0.0.1:5432/optimizer",LLM_PROVIDER="openai",FUND_PRIMARY_MODEL="gpt-4o-mini")
pgbin = next(Path("/usr/lib/postgresql").glob("*/bin"))
data=state/"pgdata"
subprocess.run([str(pgbin/"initdb"), "-D", str(data), "-A", "trust", "-U", "agent"], check=True, stdout=sys.stderr)
subprocess.run([str(pgbin/"pg_ctl"), "-D", str(data), "-l", str(state/"postgres.log"),
    "-o", "-h 127.0.0.1 -k /tmp", "-w", "start"], check=True, stdout=sys.stderr)
subprocess.run([str(pgbin/"createdb"), "-h", "127.0.0.1", "-U", "agent", "optimizer"], check=True)
os.chdir("/opt/agent/agent/packages/portopt-db")
subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True, stdout=sys.stderr)
