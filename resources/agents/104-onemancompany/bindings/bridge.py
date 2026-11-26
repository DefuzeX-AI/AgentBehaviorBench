"""Use the native local server's registered employee executor and meeting route."""
import asyncio
import os
from pathlib import Path
import subprocess
import sys


class NativeBinding:
    async def ainvoke(self, value, config=None, **kwargs):
        import httpx
        import uvicorn
        from onemancompany.main import app
        from onemancompany.core.vessel import employee_manager
        from onemancompany.core.config import EA_ID

        text = value['message'] if isinstance(value, dict) else value
        server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=8000, log_level='warning'))
        task = asyncio.create_task(server.serve())
        try:
            for _ in range(180):
                if task.done():
                    await task
                    raise RuntimeError('Native server stopped before startup completed')
                if server.started:
                    break
                await asyncio.sleep(1)
            else:
                raise RuntimeError('Native server startup timed out')
            # The route has a plain-model fallback; require its real executor instead.
            if EA_ID not in employee_manager.executors:
                raise RuntimeError('Native founding EA executor was not registered')
            async with httpx.AsyncClient(trust_env=False, timeout=240) as client:
                response = await client.post('http://127.0.0.1:8000/api/oneonone/chat',
                    json={'employee_id': EA_ID, 'message': text, 'history': []})
                response.raise_for_status()
                data = response.json()
                reply = data.get('response')
                if not reply or data.get('error') or reply.startswith('(Execution error:'):
                    raise RuntimeError(f'Native employee execution failed: {data}')
                return {'messages': [{'role': 'assistant', 'content': reply}]}
        finally:
            server.should_exit = True
            await task

    def invoke(self, value, config=None, **kwargs):
        return asyncio.run(self.ainvoke(value, config=config, **kwargs))


def create_graph():
    sys.path.insert(0, '/opt/agent/agent/src')
    state = Path.home()/'onemancompany'
    state.mkdir(parents=True, exist_ok=True)
    os.chdir(state)
    values = {'DEFAULT_API_PROVIDER': 'openai', 'DEFAULT_LLM_MODEL': 'gpt-4o-mini',
              'OPENAI_API_KEY': os.environ['OPENAI_API_KEY'], 'HOST': '127.0.0.1', 'PORT': '8000'}
    os.environ.update(values)
    env_file = state/'.env'
    env_file.write_text(''.join(f'{key}={value}\n' for key, value in values.items()), encoding='utf8')
    env_file.chmod(0o600)
    subprocess.run([sys.executable, '-m', 'onemancompany.onboard', '--auto', '--yes'],
                   check=True, stdout=sys.stderr)
    return NativeBinding()
