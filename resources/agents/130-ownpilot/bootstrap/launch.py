"""Supervise a private PostgreSQL cluster and the unchanged native ACP CLI."""
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def model_environment(environ):
    required = ('ABB_AGENT_MODEL_API_KEY', 'ABB_AGENT_MODEL_BASE_URL', 'ABB_AGENT_MODEL')
    if any(not environ.get(key, '').strip() for key in required):
        raise ValueError('Missing runtime-owned ABB model configuration')
    target = urlsplit(environ['ABB_AGENT_MODEL_BASE_URL'])
    if target.scheme not in ('http', 'https') or not target.hostname or target.username or target.password or target.query or target.fragment:
        raise ValueError('Invalid runtime-owned model base URL')
    return dict(environ)


def run(command, env):
    subprocess.run(command, env=env, check=True, stdout=sys.stderr, stderr=sys.stderr)


def main():
    env = model_environment(os.environ)
    descriptor = ROOT / 'agent/packages/core/data/providers/abb-runtime.json'
    config = json.loads(descriptor.read_text())
    config['baseUrl'] = env['ABB_AGENT_MODEL_BASE_URL'].rstrip('/')
    descriptor.write_text(json.dumps(config, indent=2) + '\n')
    child = None
    started = False
    with tempfile.TemporaryDirectory(prefix='ownpilot-pg-') as directory:
        folder = Path(directory)
        data = folder / 'data'
        password = secrets.token_hex(24)
        password_file = folder / 'password'
        password_file.write_text(password)
        password_file.chmod(0o600)
        env.update(POSTGRES_HOST='127.0.0.1', POSTGRES_PORT='25432',
                   POSTGRES_USER='ownpilot', POSTGRES_DB='ownpilot',
                   POSTGRES_PASSWORD=password, PGPASSWORD=password,
                   DATABASE_URL=f'postgresql://ownpilot:{password}@127.0.0.1:25432/ownpilot')

        def interrupted(signum, _frame):
            raise SystemExit(128 + signum)

        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, interrupted)
        try:
            run(['initdb', '-D', str(data), '-U', 'ownpilot', '--auth=scram-sha-256', '--pwfile', str(password_file)], env)
            password_file.unlink()
            run(['pg_ctl', '-D', str(data), '-l', str(folder / 'postgres.log'), '-o',
                 f"-h 127.0.0.1 -p 25432 -k {folder}", '-w', 'start'], env)
            started = True
            run(['createdb', '-h', '127.0.0.1', '-p', '25432', '-U', 'ownpilot', 'ownpilot'], env)
            child = subprocess.Popen(['node', str(ROOT / 'bootstrap/start.mjs')], env=env, start_new_session=True)
            return child.wait()
        finally:
            if child is not None and child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait()
            if started:
                subprocess.run(['pg_ctl', '-D', str(data), '-m', 'fast', '-w', 'stop'],
                               env=env, stdout=sys.stderr, stderr=sys.stderr, timeout=30)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except ValueError as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)
