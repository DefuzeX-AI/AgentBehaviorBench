"""Deploy Aurora's real database, secrets store, API, frontend and chat server."""
import os
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
    memory_events = Path("/sys/fs/cgroup/memory.events")
    if memory_events.is_file():
        parts.append("memory.events:\n" + memory_events.read_text())
    text = "\n".join(parts)[-32000:]
    values = list(extra_secrets) + [v for k, v in environment.items()
        if any(word in k.upper() for word in ("KEY", "TOKEN", "PASSWORD", "SECRET", "PASS"))]
    for value in sorted(set(str(v) for v in values if v and len(str(v)) >= 6), key=len, reverse=True):
        text = text.replace(value, "[redacted]")
    return RuntimeError(reason + ("\nNative logs:\n" + text if text else ""))

def start_deployment():
    import httpx
    import yaml
    home = Path.home()/"aurora-state"
    home.mkdir(exist_ok=True)
    search_settings = yaml.safe_load(Path("/opt/aurora-searxng/settings.yml").read_text())
    search_settings.setdefault("server", {}).update(port=8280, bind_address="127.0.0.1")
    search_settings_path = home/"searxng-settings.yml"
    search_settings_path.write_text(yaml.safe_dump(search_settings))
    password = secrets.token_urlsafe(24)
    vault_token = secrets.token_urlsafe(32)
    env = dict(os.environ, PYTHONPATH="/app", AURORA_ENV="production",
        POSTGRES_HOST="127.0.0.1", POSTGRES_PORT="5432", POSTGRES_USER="app", POSTGRES_PASSWORD=password,
        POSTGRES_DB="aurora_db", REDIS_URL="redis://127.0.0.1:6379/0",
        FLASK_SECRET_KEY=secrets.token_urlsafe(32), AUTH_SECRET=secrets.token_urlsafe(32),
        INTERNAL_API_SECRET=secrets.token_urlsafe(32), ENABLE_POD_ISOLATION="false",
        AGENT_RECURSION_LIMIT=os.environ.get("AGENT_RECURSION_LIMIT", "240"),
        SECRETS_BACKEND="vault", VAULT_TOKEN=vault_token, VAULT_ADDR="http://127.0.0.1:8200",
        VAULT_KV_MOUNT="aurora", VAULT_KV_BASE_PATH="users",
        LLM_PROVIDER_MODE="openai", MAIN_MODEL="openai/gpt-4o-mini", SUMMARIZATION_MODEL="openai/gpt-4o-mini",
        BACKEND_URL="http://127.0.0.1:5080", AUTH_URL="http://127.0.0.1:3000",
        FRONTEND_URL="http://127.0.0.1:3000", SEARXNG_URL="http://127.0.0.1:8280",
        SEARXNG_SETTINGS_PATH=str(search_settings_path), SEARXNG_SECRET=secrets.token_urlsafe(32),
        NEXTAUTH_URL="http://127.0.0.1:3000", NEXT_PUBLIC_BACKEND_URL="http://127.0.0.1:5080",
        NEXT_PUBLIC_WEBSOCKET_URL="ws://127.0.0.1:5006", NODE_ENV="production")
    processes = []
    def launch(name, argv, cwd="/app"):
        stream = (home/f"{name}.log").open("w")
        process = subprocess.Popen(argv, cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT)
        processes.append(process)
        return process
    def wait_port(port, timeout=180):
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            if any(process.poll() is not None for process in processes):
                raise startup_error(f"Aurora service exited while waiting for port {port}", sorted(home.glob("*.log")), env, [password, vault_token])
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    return
            except OSError:
                time.sleep(1)
        raise startup_error(f"Aurora service port {port} did not start", sorted(home.glob("*.log")), env, [password, vault_token])
    pg = sorted(Path("/usr/lib/postgresql").glob("*/bin"))[-1]
    pw = home/"pg-password"
    pw.write_text(password)
    pw.chmod(0o600)
    subprocess.run([str(pg/"initdb"), "-D", str(home/"pg"), "-U", "app", "--auth-host=scram-sha-256",
        "--auth-local=trust", "--pwfile="+str(pw)], check=True, stdout=subprocess.DEVNULL)
    launch("postgres", [str(pg/"postgres"), "-D", str(home/"pg"), "-h", "127.0.0.1", "-k", str(home)])
    launch("redis", ["redis-server", "--bind", "127.0.0.1", "--dir", str(home)])
    launch("vault", ["vault", "server", "-dev", "-dev-listen-address=127.0.0.1:8200", "-dev-root-token-id="+vault_token])
    for port in (5432, 6379, 8200):
        wait_port(port)
    # The native Compose PostgreSQL image creates POSTGRES_DB before app startup.
    subprocess.run([str(pg/"createdb"), "-h", "127.0.0.1", "-U", "app", "aurora_db"],
        env=dict(env, PGPASSWORD=password), check=True, stdout=subprocess.DEVNULL)
    with httpx.Client(trust_env=False, timeout=20) as client:
        response = client.post("http://127.0.0.1:8200/v1/sys/mounts/aurora",
            headers={"X-Vault-Token": vault_token}, json={"type": "kv", "options": {"version": "2"}})
        response.raise_for_status()
    launch("searxng", ["/opt/searxng-venv/bin/searxng-run"])
    wait_port(8280)
    launch("compute", ["gunicorn", "main_compute:app", "--bind", "127.0.0.1:5080", "--workers", "1", "--threads", "8", "--timeout", "300"])
    wait_port(5080)
    with httpx.Client(trust_env=False, timeout=5) as client:
        deadline = time.monotonic()+180
        while time.monotonic() < deadline:
            if any(process.poll() is not None for process in processes):
                raise startup_error("Aurora service exited before API readiness", sorted(home.glob("*.log")), env, [password, vault_token])
            try:
                if client.get("http://127.0.0.1:5080/health/readiness").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)
        else:
            raise startup_error("Aurora API readiness deadline exceeded", sorted(home.glob("*.log")), env, [password, vault_token])
    launch("chatbot", [sys.executable, "main_chatbot.py"])
    launch("frontend", ["bun", "run", "start", "--hostname", "127.0.0.1"], "/opt/aurora-client")
    for port in (5006, 3000):
        wait_port(port)
    def diagnostics(reason, additional_secrets=()):
        return startup_error(reason, sorted(home.glob("*.log")), env,
            [password, vault_token, *additional_secrets])
    return processes, diagnostics
