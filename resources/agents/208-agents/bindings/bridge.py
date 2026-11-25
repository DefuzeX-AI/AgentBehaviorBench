"""Use the native first-run setup, vault and tenant-scoped Playground API."""
import http.cookiejar
import json
import os
from pathlib import Path
import re
import secrets
import ssl
import subprocess
import sys
import time
import urllib.request


class NativeBinding:
    def __init__(self, opener, tenant, agent_id):
        self.opener, self.tenant, self.agent_id = opener, tenant, agent_id

    def invoke(self, value, config=None):
        text = value.get("message", "") if isinstance(value, dict) else str(value)
        result = request(self.opener, "/v1/agents/"+self.agent_id+"/playground", {"message": text}, self.tenant)
        if not result.get("reply") or result.get("suppressed"):
            raise RuntimeError("Native Playground returned no visible reply")
        return result


def request(opener, path, payload=None, tenant=None):
    headers = {"Content-Type": "application/json", "Origin": "https://127.0.0.1:8443"}
    if tenant:
        headers["X-Tenant-Id"] = tenant
    req = urllib.request.Request("https://127.0.0.1:8443/api"+path,
        data=json.dumps(payload).encode() if payload is not None else None, headers=headers)
    with opener.open(req, timeout=300) as response:
        return json.load(response)


def create_graph():
    root = Path("/opt/agent/agent")
    state = Path.home()/"fazer-agents"
    state.mkdir(parents=True, exist_ok=True)
    pgbin = next(Path("/usr/lib/postgresql").glob("*/bin"))
    data = state/"pgdata"
    subprocess.run([str(pgbin/"initdb"), "-D", str(data), "-A", "trust", "-U", "agent"], check=True, stdout=sys.stderr)
    subprocess.run([str(pgbin/"pg_ctl"), "-D", str(data), "-l", str(state/"postgres.log"),
        "-o", "-h 127.0.0.1 -k /tmp", "-w", "start"], check=True, stdout=sys.stderr)
    subprocess.run([str(pgbin/"createdb"), "-h", "127.0.0.1", "-U", "agent", "fazer"], check=True)
    os.environ.update(NODE_ENV="production", PORT="3000", PUBLIC_URL="https://127.0.0.1:8443",
        DATABASE_URL="postgresql://app:"+secrets.token_hex(24)+"@127.0.0.1:5432/fazer",
        MIGRATION_DATABASE_URL="postgresql://agent@127.0.0.1:5432/fazer",
        JWT_SECRET=secrets.token_hex(32), ENCRYPTION_KEY=secrets.token_hex(32))
    subprocess.run(["bun", "scripts/db-boot.ts"], cwd=root, check=True, stdout=sys.stderr)
    log_path = state/"server.log"
    log = log_path.open("w")
    server = subprocess.Popen(["bun", "src/index.ts"], cwd=root, stdout=log, stderr=log)
    certificate, private_key = state/"localhost.crt", state/"localhost.key"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
        "-keyout", str(private_key), "-out", str(certificate), "-subj", "/CN=localhost",
        "-addext", "subjectAltName=IP:127.0.0.1,DNS:localhost"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    nginx_config = state/"nginx.conf"
    nginx_config.write_text(f'''pid {state}/nginx.pid;
error_log {state}/nginx.log;
events {{ worker_connections 64; }}
http {{ access_log off; client_body_temp_path {state}/client_temp;
proxy_temp_path {state}/proxy_temp;
fastcgi_temp_path {state}/fastcgi_temp;
uwsgi_temp_path {state}/uwsgi_temp;
scgi_temp_path {state}/scgi_temp;
server {{ listen 127.0.0.1:8443 ssl; ssl_certificate {certificate}; ssl_certificate_key {private_key};
location / {{ proxy_pass http://127.0.0.1:3000; proxy_set_header Host $http_host;
proxy_set_header X-Forwarded-Proto https; proxy_read_timeout 600s; }} }} }}
''')
    subprocess.run(["nginx", "-p", str(state), "-c", str(nginx_config)], check=True)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
        urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=str(certificate))))
    deadline = time.monotonic()+180
    token = None
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise RuntimeError("Native fazer-ai server exited before setup")
        match = re.search(r'/setup\?token=([A-Za-z0-9_-]+)', log_path.read_text(errors="replace"))
        if match:
            try:
                request(opener, "/health")
                token = match.group(1)
                break
            except OSError:
                pass
        time.sleep(0.5)
    if not token:
        raise RuntimeError("Native first-run setup token/readiness unavailable")
    setup = request(opener, "/auth/setup", {"email": "abb-local@example.invalid",
        "password": secrets.token_urlsafe(32), "name": "ABB local operator", "token": token})
    tenant = setup["defaultTenantId"]
    vault = request(opener, "/v1/vault", {"name": "ABB model route", "value": os.environ["OPENAI_API_KEY"]}, tenant)
    agent = request(opener, "/v1/agents", {"name": "ABB native greeting", "modelConfig": {
        "provider": "openai", "model": "gpt-4o-mini", "credentialRef": vault["ref"],
        "baseURL": "https://api.openai.com/v1"}}, tenant)
    return NativeBinding(opener, tenant, str(agent["agent"]["id"]))
