"""Start a real local PostgreSQL/pgvector database for native persistent memory."""
import os
from pathlib import Path
import subprocess
import sys

state = Path.home()/'gpt-home'
state.mkdir(parents=True, exist_ok=True)
os.environ['DATABASE_URL'] = 'postgresql://agent@127.0.0.1:5432/gpt_home'
pgbin = next(Path('/usr/lib/postgresql').glob('*/bin'))
data = state/'pgdata'
subprocess.run([str(pgbin/'initdb'), '-D', str(data), '-A', 'trust', '-U', 'agent'], check=True, stdout=sys.stderr)
subprocess.run([str(pgbin/'pg_ctl'), '-D', str(data), '-l', str(state/'postgres.log'),
    '-o', '-h 127.0.0.1 -k /tmp', '-w', 'start'], check=True, stdout=sys.stderr)
subprocess.run([str(pgbin/'createdb'), '-h', '127.0.0.1', '-U', 'agent', 'gpt_home'], check=True)
subprocess.run([str(pgbin/'psql'), '-h', '127.0.0.1', '-U', 'agent', '-d', 'gpt_home',
    '-c', 'CREATE EXTENSION IF NOT EXISTS vector'], check=True, stdout=sys.stderr)
os.chdir('/opt/agent/agent')
