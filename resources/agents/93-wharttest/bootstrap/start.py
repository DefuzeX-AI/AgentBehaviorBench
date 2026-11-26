"""Provision real native application state and start its ASGI endpoint."""
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import httpx

root = Path("/opt/agent/agent/WHartTest_Django")
state = Path.home()/"wharttest"
state.mkdir(parents=True, exist_ok=True)
os.chdir(root)
database_password = secrets.token_urlsafe(24)
os.environ.update(DJANGO_SETTINGS_MODULE="wharttest_django.settings",
    DJANGO_SECRET_KEY=secrets.token_urlsafe(32), DJANGO_DEBUG="False",
    DJANGO_ALLOWED_HOSTS="127.0.0.1,localhost", DATABASE_TYPE="postgres",
    POSTGRES_HOST="127.0.0.1", POSTGRES_PORT="5432", POSTGRES_DB="wharttest",
    POSTGRES_USER="agent", POSTGRES_PASSWORD=database_password,
    MEDIA_ROOT=str(state/"media"), CELERY_BROKER_URL="redis://127.0.0.1:6379/0",
    CELERY_RESULT_BACKEND="redis://127.0.0.1:6379/1", UI_AUTOMATION_REDIS_URL="redis://127.0.0.1:6379/0")
pgbin = Path("/usr/lib/postgresql/15/bin")
password_file = state/"postgres-password"
password_file.write_text(database_password)
password_file.chmod(0o600)
subprocess.run([str(pgbin/"initdb"), "-D", str(state/"pgdata"), "-U", "agent",
    "--auth-local=trust", "--auth-host=scram-sha-256", "--pwfile="+str(password_file)],
    check=True, stdout=sys.stderr)
subprocess.run([str(pgbin/"pg_ctl"), "-D", str(state/"pgdata"), "-l", str(state/"postgres.log"),
    "-o", "-h 127.0.0.1 -k /tmp", "-w", "start"], check=True, stdout=sys.stderr)
subprocess.run([str(pgbin/"createdb"), "-h", "127.0.0.1", "-U", "agent", "wharttest"],
    env=dict(os.environ, PGPASSWORD=database_password), check=True, stdout=sys.stderr)
subprocess.run(["redis-server", "--bind", "127.0.0.1", "--daemonize", "yes", "--dir", str(state),
    "--logfile", str(state/"redis.log")], check=True)
import django
django.setup()
from django.core.management import call_command
call_command("migrate", interactive=False, verbosity=0)
from django.contrib.auth import get_user_model
from projects.models import Project, ProjectMember
from langgraph_integration.models import LLMConfig
from rest_framework_simplejwt.tokens import RefreshToken
user = get_user_model().objects.create_user(username="abb-local", password=secrets.token_urlsafe(24))
project = Project.objects.create(name="ABB greeting workspace", creator=user)
ProjectMember.objects.get_or_create(project=project, user=user, defaults={"role": "owner"})
LLMConfig.objects.create(config_name="ABB model", provider="openai_compatible", name="gpt-4o-mini",
    api_url="https://api.openai.com/v1", api_key=os.environ["OPENAI_API_KEY"], is_active=True)
log = (state/"asgi.log").open("w")
server = subprocess.Popen([sys.executable, "-m", "uvicorn", "wharttest_django.asgi:application",
    "--host", "127.0.0.1", "--port", "8000"], stdout=log, stderr=log)
celery_log = (state/"celery.log").open("w")
celery = subprocess.Popen([sys.executable, "-m", "celery", "-A", "wharttest_django", "worker",
    "--pool", "solo", "--concurrency", "1", "--loglevel", "WARNING"], stdout=celery_log, stderr=celery_log)
for _ in range(60):
    if server.poll() is not None:
        raise RuntimeError("Native ASGI startup failed: " + (state/"asgi.log").read_text()[-5000:])
    try:
        with httpx.Client(trust_env=False, timeout=2) as client:
            client.get("http://127.0.0.1:8000/")
        break
    except httpx.TransportError:
        time.sleep(1)
else:
    raise RuntimeError("Native ASGI endpoint did not become ready")
deployment = {"token": str(RefreshToken.for_user(user).access_token),
    "project_id": project.pk, "processes": [server, celery]}
