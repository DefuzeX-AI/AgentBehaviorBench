"""Start real infrastructure and GAIA's native self-host API and worker."""
import os
import json
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time



def startup_error(reason, paths, environment, extra_secrets=()):
    """Retain bounded native startup evidence after container teardown."""
    parts = []
    for path in paths:
        if path.is_file():
            parts.append(path.name + ":\n" + path.read_text(errors="replace")[-4000:])
    for name in ("memory.events", "pids.current", "pids.max", "pids.events"):
        counter = Path("/sys/fs/cgroup")/name
        if counter.is_file():
            parts.append(name + ":\n" + counter.read_text())
    text = "\n".join(parts)[-32000:]
    values = list(extra_secrets) + [v for k, v in environment.items()
        if any(word in k.upper() for word in ("KEY", "TOKEN", "PASSWORD", "SECRET", "PASS"))]
    for value in sorted(set(str(v) for v in values if v and len(str(v)) >= 6), key=len, reverse=True):
        text = text.replace(value, "[redacted]")
    return RuntimeError(reason + ("\nNative logs:\n" + text if text else ""))

def start_deployment():
    home = Path.home()/"gaia-state"
    home.mkdir(exist_ok=True)
    # This deployment uses one local RabbitMQ node. Resolve its own name on
    # loopback instead of asking the container's external DNS resolver.
    rabbit_inetrc = home/"rabbit-inetrc"
    rabbit_aliases = json.dumps(["localhost", socket.gethostname()])
    rabbit_inetrc.write_text(
        '{lookup, [file]}.\n'
        '{host, {127,0,0,1}, ' + rabbit_aliases + '}.\n'
    )
    password = secrets.token_urlsafe(24)
    env = dict(os.environ, ENV="selfhost", AUTH_MODE="local", BLOB_STORE="local",
        PYTHONPATH="/app/apps/api:/app/libs",
        MONGO_DB="mongodb://127.0.0.1:27017/gaia", REDIS_URL="redis://127.0.0.1:6379/0",
        CHROMADB_HOST="127.0.0.1", CHROMADB_PORT="8001",
        POSTGRES_URL=f"postgresql://appuser:{password}@127.0.0.1:5432/langgraph",
        RABBITMQ_URL=f"amqp://abb:{password}@127.0.0.1:5672/",
        AGENT_SECRET=secrets.token_urlsafe(32), BOT_SESSION_TOKEN_SECRET=secrets.token_urlsafe(32),
        EMAIL_UNSUBSCRIBE_SECRET=secrets.token_urlsafe(32),
        RABBITMQ_DEFAULT_USER="abb", RABBITMQ_DEFAULT_PASS=password,
        RABBITMQ_MNESIA_BASE=str(home/"rabbit-db"), RABBITMQ_LOG_BASE=str(home/"rabbit-logs"),
        RABBITMQ_NODENAME="rabbit@localhost", RABBITMQ_LOGS="-",
        RABBITMQ_SERVER_ADDITIONAL_ERL_ARGS="+S 2:2 +SDcpu 1 +SDio 1 +A 2",
        GLIBC_TUNABLES="glibc.pthread.rseq=0",
        OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
        NUMEXPR_NUM_THREADS="1", RAYON_NUM_THREADS="1", TOKIO_WORKER_THREADS="2")
    processes = []
    def launch(name, argv, extra=None):
        stream = (home/f"{name}.log").open("w")
        process = subprocess.Popen(argv, cwd="/app/apps/api", env=dict(env, **(extra or {})),
            stdout=stream, stderr=subprocess.STDOUT)
        processes.append(process)
        return process
    def wait_port(port, seconds=120):
        deadline = time.monotonic()+seconds
        while time.monotonic() < deadline:
            if any(process.poll() is not None for process in processes):
                raise startup_error(f"Native service exited while waiting for port {port}", sorted(home.glob("*.log")), env, [password])
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    return
            except OSError:
                time.sleep(1)
        raise startup_error(f"Native infrastructure port {port} did not start", sorted(home.glob("*.log")), env, [password])
    for name in ("mongo", "chroma", "rabbit-db", "rabbit-logs"):
        (home/name).mkdir(exist_ok=True)
    pg = sorted(Path("/usr/lib/postgresql").glob("*/bin"))[-1]
    pw = home/"pg-password"
    pw.write_text(password)
    pw.chmod(0o600)
    subprocess.run([str(pg/"initdb"), "-D", str(home/"pg"), "-U", "appuser",
        "--auth-host=scram-sha-256", "--auth-local=trust", "--pwfile="+str(pw)], check=True,
        stdout=subprocess.DEVNULL)
    launch("postgres", [str(pg/"postgres"), "-D", str(home/"pg"), "-h", "127.0.0.1", "-k", str(home)])
    wait_port(5432)
    subprocess.run([str(pg/"createdb"), "-h", str(home), "-U", "appuser", "langgraph"], check=True)
    launch("redis", ["redis-server", "--bind", "127.0.0.1", "--dir", str(home)])
    launch("mongo", ["mongod", "--bind_ip", "127.0.0.1", "--dbpath", str(home/"mongo")])
    launch("rabbit", ["/usr/sbin/rabbitmq-server"], {"ERL_INETRC": str(rabbit_inetrc)})
    launch("chroma", ["/opt/chroma/bin/chroma", "run", "--host", "127.0.0.1", "--port", "8001", "--path", str(home/"chroma")])
    for port in (6379, 27017, 5672, 8001):
        wait_port(port)
    subprocess.run([sys.executable, "-m", "scripts.migrate_conversations"], cwd="/app/apps/api", env=env,
        check=True, stdout=(home/"migration.log").open("w"), stderr=subprocess.STDOUT)
    launch("worker", [sys.executable, "-m", "arq", "app.worker.WorkerSettings",
        "--custom-log-dict", "app.workers.config.log_config.ARQ_LOG_CONFIG"],
        {"WORKER_TYPE": "arq_worker", "GAIA_SERVICE_NAME": "arq_worker"})
    launch("api", [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        {"WORKER_TYPE": "main_app"})
    wait_port(8000, 180)
    return processes
