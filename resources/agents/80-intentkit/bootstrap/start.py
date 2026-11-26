"""Start disposable loopback PostgreSQL/Redis before the ABB worker."""
import os
from pathlib import Path
import subprocess
import sys
home = Path.home()
state = home / "intentkit"
state.mkdir(parents=True, exist_ok=True)
os.environ.update(DB_HOST="127.0.0.1", DB_USERNAME="agent", DB_PASSWORD="",
    DB_NAME="intentkit", DB_PORT="5432", REDIS_HOST="127.0.0.1",
    OPENAI_COMPATIBLE_BASE_URL="https://api.openai.com/v1",
    OPENAI_COMPATIBLE_MODEL="gpt-4o-mini", OPENAI_COMPATIBLE_MODEL_LITE="gpt-4o-mini")
pgbin = next(Path("/usr/lib/postgresql").glob("*/bin"))
data = state / "pgdata"
subprocess.run([str(pgbin / "initdb"), "-D", str(data), "-A", "trust", "-U", "agent"], check=True, stdout=sys.stderr)
subprocess.run([str(pgbin / "pg_ctl"), "-D", str(data), "-l", str(state/"postgres.log"),
    "-o", "-h 127.0.0.1 -k /tmp", "-w", "start"], check=True, stdout=sys.stderr)
subprocess.run([str(pgbin/"createdb"), "-h", "127.0.0.1", "-U", "agent", "intentkit"], check=True)
subprocess.run(["redis-server", "--bind", "127.0.0.1", "--daemonize", "yes", "--dir", str(state),
    "--logfile", str(state/"redis.log")], check=True)
