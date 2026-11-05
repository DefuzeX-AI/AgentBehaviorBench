"""Configure the published Xiuper ACP server using ABB's selected model."""
from __future__ import annotations
import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlsplit

KEY = 'ABB_AGENT_MODEL_API_KEY'
BASE = 'ABB_AGENT_MODEL_BASE_URL'
MODEL = 'ABB_AGENT_MODEL'
COMMAND = ['node', '/opt/agent/agent/node_modules/@xiuper/cli/dist/jsMain/typescript/index.js', 'acp']

def selected(environ):
    for name in (KEY, BASE, MODEL):
        if not environ.get(name, '').strip():
            raise ValueError(name + ' is required')
    base = environ[BASE].strip().rstrip('/')
    url = urlsplit(base)
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError('Selected model endpoint must be a credential-free HTTPS URL')
    model = environ[MODEL].strip()
    if any(c.isspace() for c in model):
        raise ValueError('Selected model identifier must not contain whitespace')
    return base, model

def prepare(environ, home):
    base, model = selected(environ)
    # Native ConfigManager accepts JSON as YAML. Keep its credential file private,
    # outside the Case workspace, and write it only inside the disposable container.
    directory = Path(home) / '.autodev'
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    config = {'active':'abb', 'configs':[{'name':'abb', 'provider':'custom-openai-base',
              'model':model, 'baseUrl':base + '/', 'apiKey':environ[KEY]}], 'mcpServers':{}}
    path = directory / 'config.yaml'
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(config, stream)
    child = dict(environ)
    child['HOME'] = str(home)
    if child.get('SSL_CERT_FILE'):
        child['NODE_EXTRA_CA_CERTS'] = child['SSL_CERT_FILE']
    return list(COMMAND), child

def main():
    try:
        environ = dict(os.environ)
        selected(environ)
        home = tempfile.mkdtemp(prefix='abb-autodev-home-')
        command, child = prepare(environ, home)
    except (ValueError, OSError) as exc:
        print(str(exc).replace(os.environ.get(KEY) or '\0', '[REDACTED]'), file=sys.stderr)
        return 1
    os.execvpe(command[0], command, child)

if __name__ == '__main__':
    raise SystemExit(main())
