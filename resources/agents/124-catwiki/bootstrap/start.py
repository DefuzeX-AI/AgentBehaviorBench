"""Provision an actual isolated PostgreSQL database and native migrations."""
import os
from pathlib import Path
import secrets
import subprocess
import sys
state = Path.home()/"catwiki"
state.mkdir(parents=True, exist_ok=True)
os.environ.update(POSTGRES_SERVER="127.0.0.1", POSTGRES_USER="agent", POSTGRES_PASSWORD="", POSTGRES_DB="catwiki")
pgbin = next(Path("/usr/lib/postgresql").glob("*/bin"))
data=state/"pgdata"
subprocess.run([str(pgbin/"initdb"), "-D", str(data), "-A", "trust", "-U", "agent"], check=True, stdout=sys.stderr)
subprocess.run([str(pgbin/"pg_ctl"), "-D", str(data), "-l", str(state/"postgres.log"),
    "-o", "-h 127.0.0.1 -k /tmp", "-w", "start"], check=True, stdout=sys.stderr)
subprocess.run([str(pgbin/"createdb"), "-h", "127.0.0.1", "-U", "agent", "catwiki"], check=True)
os.chdir("/opt/agent/agent/backend")
subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True, stdout=sys.stderr)
