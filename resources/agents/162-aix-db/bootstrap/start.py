"""Provision the application's real disposable database and Redis service."""
import os
from pathlib import Path
import secrets
import subprocess
import sys

state = Path.home()/"aix-db"
state.mkdir(parents=True, exist_ok=True)
os.environ["SQLALCHEMY_DATABASE_URI"] = "postgresql+psycopg2://agent@127.0.0.1:5432/aix_db"
os.environ["JWT_SECRET_KEY"] = secrets.token_urlsafe(32)
pgbin = next(Path("/usr/lib/postgresql").glob("*/bin"))
data = state/"pgdata"
subprocess.run([str(pgbin/"initdb"), "-D", str(data), "-A", "trust", "-U", "agent"], check=True, stdout=sys.stderr)
subprocess.run([str(pgbin/"pg_ctl"), "-D", str(data), "-l", str(state/"postgres.log"),
    "-o", "-h 127.0.0.1 -k /tmp", "-w", "start"], check=True, stdout=sys.stderr)
subprocess.run([str(pgbin/"createdb"), "-h", "127.0.0.1", "-U", "agent", "aix_db"], check=True)
subprocess.run([str(pgbin/"psql"), "-h", "127.0.0.1", "-U", "agent", "-d", "aix_db",
    "-c", "CREATE EXTENSION IF NOT EXISTS vector"], check=True, stdout=sys.stderr)
subprocess.run(["redis-server", "--bind", "127.0.0.1", "--daemonize", "yes", "--dir", str(state),
    "--logfile", str(state/"redis.log")], check=True)
os.chdir("/opt/agent/agent")
