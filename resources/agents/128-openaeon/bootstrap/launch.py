"""Configure and supervise the unchanged native OpenAEON Gateway and ACP bridge."""
from __future__ import annotations
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit


def prepare(environ, home, workspace, *, source=Path('/opt/agent/agent'), compile_cache=Path('/opt/openaeon-node-cache'),
            jiti_cache=Path('/opt/openaeon-jiti-cache')):
    for key in ('ABB_AGENT_MODEL', 'ABB_AGENT_MODEL_BASE_URL', 'ABB_AGENT_MODEL_API_KEY'):
        if not environ.get(key, '').strip():
            raise ValueError(key + ' is required')
    model = environ['ABB_AGENT_MODEL'].strip()
    base = environ['ABB_AGENT_MODEL_BASE_URL'].strip().rstrip('/')
    url = urlsplit(base)
    if (url.scheme != 'https' or not url.hostname or url.username or url.password
            or url.query or url.fragment or any(c.isspace() for c in base)):
        raise ValueError('Selected model requires an HTTPS base URL without embedded credentials or URL parameters')
    if any(ord(c) < 32 for c in model):
        raise ValueError('Selected model must not contain control characters')
    home = Path(home); home.mkdir(mode=0o700, parents=True, exist_ok=True)
    home.chmod(0o700)
    workspace = Path(workspace).resolve()
    if not workspace.is_dir():
        raise ValueError('The declared workspace must exist')
    state = home / '.openaeon'; state.mkdir(mode=0o700, exist_ok=False)
    token = secrets.token_urlsafe(32)
    token_file = state / 'gateway.token'; token_file.write_text(token); token_file.chmod(0o600)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    selected = 'abb/' + model
    config = {
        'gateway': {'mode': 'local', 'bind': 'loopback', 'port': port,
                    'auth': {'mode': 'token', 'token': token}, 'controlUi': {'enabled': False}},
        'models': {'mode': 'replace', 'providers': {'abb': {
            'baseUrl': base, 'apiKey': '${ABB_AGENT_MODEL_API_KEY}',
            'api': 'openai-completions', 'auth': 'api-key',
            'models': [{'id': model, 'name': model, 'reasoning': False, 'input': ['text'],
                        'contextWindow': 128000, 'maxTokens': 4096,
                        'cost': {'input': 0, 'output': 0, 'cacheRead': 0, 'cacheWrite': 0},
                        'compat': {'maxTokensField': 'max_tokens'}}]}}},
        'agents': {'defaults': {'workspace': str(workspace),
            'model': {'primary': selected, 'fallbacks': []},
            'imageModel': {'primary': selected, 'fallbacks': []},
            'models': {selected: {}}, 'subagents': {'model': {'primary': selected, 'fallbacks': []}},
            'heartbeat': {'every': '0m', 'model': selected}, 'timeoutSeconds': 600}},
    }
    path = state / 'openaeon.json'; path.write_text(json.dumps(config)); path.chmod(0o600)
    cache_home = home / '.cache/node-compile'
    cache_home.mkdir(mode=0o700, parents=True)
    if Path(compile_cache).is_dir():
        # Public bytecode cache only: native JS source, config and tools are unchanged.
        shutil.copytree(compile_cache, cache_home, dirs_exist_ok=True)
    jiti_home = home / '.cache/jiti'
    jiti_home.mkdir(mode=0o700, parents=True)
    if Path(jiti_cache).is_dir():
        shutil.copytree(jiti_cache, jiti_home, dirs_exist_ok=True)
    env = dict(environ)
    for key in list(env):
        if key.startswith(('OPENCLAW_', 'OPENAEON_', 'AEONPROPHET_')) or key in (
                'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'DEEPSEEK_API_KEY',
                'OPENCODE_API_KEY', 'OPENROUTER_API_KEY', 'GOOGLE_API_KEY', 'GEMINI_API_KEY'):
            env.pop(key, None)
    env.update(HOME=str(home), OPENAEON_STATE_DIR=str(state), OPENAEON_CONFIG_PATH=str(path),
               OPENAEON_GATEWAY_TOKEN=token, NODE_OPTIONS='--max-old-space-size=384',
               NODE_COMPILE_CACHE=str(cache_home), JITI_FS_CACHE='true', TMPDIR=str(home / '.cache'))
    native = ['node', str(Path(source) / 'openaeon.mjs')]
    gateway = native + ['gateway', 'run', '--bind', 'loopback', '--port', str(port)]
    session_key = 'agent:main:abb-' + secrets.token_hex(8)
    metadata = home / 'abb-native-session.json'
    metadata.write_text(json.dumps({'session_key':session_key,'state_dir':str(state)}))
    metadata.chmod(0o600)
    acp = native + ['acp', '--url', 'ws://127.0.0.1:' + str(port), '--token-file', str(token_file),
                    '--session', session_key, '--verbose']
    return gateway, acp, env, port


def stop(process):
    """Stop only the owned process group with a finite TERM/KILL budget."""
    if process is None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=4)


def wait_gateway(process, port, timeout=180):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError('Native Gateway exited before accepting connections')
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError('Native Gateway startup exceeded its declared budget')


def tee_native_stderr(stream, path):
    """Retain original native session mapping while forwarding exact stderr bytes."""
    with Path(path).open('ab') as saved:
        while True:
            chunk=os.read(stream.fileno(),8192)
            if not chunk:
                return
            saved.write(chunk);saved.flush()
            sys.stderr.buffer.write(chunk);sys.stderr.buffer.flush()


def main():
    gateway = acp = None
    stderr_thread = None
    home = Path(tempfile.mkdtemp(prefix='abb-openaeon-'))
    def interrupted(signum, frame):
        raise SystemExit(128 + signum)
    signal.signal(signal.SIGTERM, interrupted); signal.signal(signal.SIGINT, interrupted)
    try:
        gcmd, acmd, env, port = prepare(os.environ, home, Path.cwd())
        # No model/tool implementation is replaced. ACP stdout remains byte-for-byte native.
        gateway = subprocess.Popen(gcmd, env=env, stdin=subprocess.DEVNULL,
                                   stdout=sys.stderr, stderr=sys.stderr, start_new_session=True)
        wait_gateway(gateway, port)
        acp = subprocess.Popen(acmd, env=env, stdin=sys.stdin, stdout=sys.stdout,
                               stderr=subprocess.PIPE, start_new_session=True)
        stderr_thread=threading.Thread(target=tee_native_stderr,args=(acp.stderr,home/'acp-native.stderr.log'),daemon=True)
        stderr_thread.start()
        while acp.poll() is None:
            if gateway.poll() is not None:
                raise RuntimeError('Native Gateway exited during the ACP session')
            time.sleep(0.1)
        return acp.returncode
    finally:
        stop(acp); stop(gateway)
        if stderr_thread is not None:
            stderr_thread.join(timeout=2)


if __name__ == '__main__':
    raise SystemExit(main())
