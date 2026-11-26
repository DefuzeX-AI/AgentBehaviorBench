"""Use the real Chainlit server and its UI protocol, including native admission."""
import asyncio
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys
import uuid


class NativeBinding:
    async def ainvoke(self, value, config=None, **kwargs):
        import httpx
        import socketio
        text = value['message'] if isinstance(value, dict) else value
        process = subprocess.Popen(['chainlit', 'run', 'main.py', '--headless',
            '--host', '127.0.0.1', '--port', '8000'], cwd='/opt/agent/agent',
            stdout=sys.stderr, stderr=sys.stderr)
        client = socketio.AsyncClient(reconnection=False)
        steps = {}
        done = asyncio.Event()
        started = False

        @client.on('new_message')
        async def new_message(data):
            steps[data['id']] = data

        @client.on('update_message')
        async def update_message(data):
            steps.setdefault(data['id'], {}).update(data)

        @client.on('task_start')
        async def task_start(*args):
            nonlocal started
            started = True

        @client.on('task_end')
        async def task_end(*args):
            if started:
                done.set()

        @client.on('ask')
        async def ask(data):
            # The greeting must not manufacture further user answers/approvals.
            return None

        try:
            async with httpx.AsyncClient(trust_env=False) as http:
                for _ in range(120):
                    if process.poll() is not None:
                        raise RuntimeError('Native Chainlit server exited during startup')
                    try:
                        response = await http.get('http://127.0.0.1:8000/health')
                        if response.status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(1)
                else:
                    raise RuntimeError('Native Chainlit startup timed out')
            await client.connect('http://127.0.0.1:8000', transports=['websocket'],
                socketio_path='ws/socket.io', headers={
                    'X-Chainlit-Session-Id': str(uuid.uuid4()),
                    'X-Chainlit-Client-Type': 'webapp', 'User-Env': '{}'})
            await client.emit('connection_successful')
            await asyncio.wait_for(done.wait(), timeout=120)
            errors = [s.get('output') for s in steps.values() if s.get('isError') or s.get('name') == 'Error']
            if errors:
                raise RuntimeError(f'Native chat initialization failed: {errors}')
            # Startup's native /start greeting is not the answer to this input.
            steps.clear()
            done.clear()
            started = False
            await client.emit('ui_message', {'message': {
                'id': str(uuid.uuid4()), 'name': 'User', 'type': 'user_message',
                'output': text, 'createdAt': datetime.now(timezone.utc).isoformat()},
                'fileReferences': []})
            await asyncio.wait_for(done.wait(), timeout=180)
            errors = [s.get('output') for s in steps.values() if s.get('isError') or s.get('name') == 'Error']
            replies = [s.get('output') for s in steps.values()
                       if s.get('type') == 'assistant_message' and s.get('output')]
            if errors or not replies:
                raise RuntimeError(f'Native chat failed: {errors or "no assistant reply"}')
            return {'messages': [{'role': 'assistant', 'content': '\n\n'.join(replies)}]}
        finally:
            if client.connected:
                await client.disconnect()
            process.terminate()
            try:
                await asyncio.to_thread(process.wait, 10)
            except subprocess.TimeoutExpired:
                process.kill()
                await asyncio.to_thread(process.wait)

    def invoke(self, value, config=None, **kwargs):
        return asyncio.run(self.ainvoke(value, config=config, **kwargs))


def create_graph():
    import yaml
    path = Path('/opt/agent/agent/config/config.yaml')
    data = yaml.safe_load(path.read_text())
    data['OPENAI_API_KEY'] = os.environ['OPENAI_API_KEY']
    # No LangSmith account was supplied. ABB still records model traffic.
    data['LANGCHAIN_TRACING_V2'] = 'false'
    path.write_text(yaml.safe_dump(data), encoding='utf8')
    path.chmod(0o600)
    return NativeBinding()
