"""Start disposable loopback PostgreSQL/Redis before the ABB worker."""
import os
from pathlib import Path
import secrets
import subprocess
import sys
home = Path.home()
state = home / "yuxi"
state.mkdir(parents=True, exist_ok=True)
for key, value in {
    "POSTGRES_URL": "postgresql+psycopg://agent@127.0.0.1:5432/yuxi",
    "REDIS_URL": "redis://127.0.0.1:6379/0",
    "YUXI_RUNTIME_DIR": str(state / "runtime"),
    "YUXI_USER_DATA_DIR": str(state / "user-data"),
    "YUXI_SKILL_DATA_DIR": str(state / "skill-sources"),
    "YUXI_SKILL_PROJECTION_DIR": str(state / "skill-projections"),
    "YUXI_PUBLIC_URL": "http://127.0.0.1:8000",
}.items():
    os.environ[key] = value
for key in ("JWT_SECRET_KEY", "API_KEY_DERIVATION_SECRET", "SANDBOX_RUNNER_TOKEN"):
    os.environ[key] = secrets.token_urlsafe(32)
pgbin = next(Path("/usr/lib/postgresql").glob("*/bin"))
data = state / "pgdata"
subprocess.run([str(pgbin / "initdb"), "-D", str(data), "-A", "trust", "-U", "agent"], check=True, stdout=sys.stderr)
subprocess.run([str(pgbin / "pg_ctl"), "-D", str(data), "-l", str(state/"postgres.log"),
    "-o", "-h 127.0.0.1 -k /tmp", "-w", "start"], check=True, stdout=sys.stderr)
subprocess.run([str(pgbin/"createdb"), "-h", "127.0.0.1", "-U", "agent", "yuxi"], check=True)
subprocess.run(["redis-server", "--bind", "127.0.0.1", "--daemonize", "yes", "--dir", str(state),
    "--logfile", str(state/"redis.log")], check=True)
