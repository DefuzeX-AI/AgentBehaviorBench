"""Opt-in real native process faults against a loopback model, no Internet/key.

Run inside the built MiniMax image with --network none. This deliberately tests
native failure/cleanup semantics separately from official Judge acceptance.
"""
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
import time
from agentbench.adapter.acp.config import ACPConfig
from agentbench.adapter.acp.session import ACPSession


class Model(BaseHTTPRequestHandler):
    scenario = '401'
    seen = threading.Event()
    requests = 0
    def log_message(self, *args): pass
    def do_POST(self):
        length = int(self.headers.get('content-length', '0'))
        self.rfile.read(length)
        if 'count_tokens' in self.path or 'input_tokens' in self.path:
            self.reply(200, {'input_tokens': 10});return
        type(self).requests += 1
        self.seen.set()
        if self.scenario in ('timeout', 'cancel'):
            time.sleep(20)
        else:
            self.reply(int(self.scenario), {'type':'error','error':{
                'type':'authentication_error' if self.scenario=='401' else 'rate_limit_error',
                'message':'isolated acceptance fault'}})
    def reply(self,status,payload):
        data=json.dumps(payload).encode()
        self.send_response(status);self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(data)));self.end_headers()
        try:self.wfile.write(data)
        except (BrokenPipeError,ConnectionResetError):pass


async def check(unit, scenario):
    Model.scenario=scenario;Model.seen.clear();Model.requests=0
    config=ACPConfig(unit,('python',str(unit/'bootstrap/launch.py')),'/home/agent/workspace',
        env_keys=('MINIMAX_API_KEY','MINIMAX_DATA_DIR','MAVIS_REGION'),timeout=12,
        handshake_timeout=10,cleanup_timeout=1)
    session=ACPSession(config)
    outcome=None
    try:
        task=asyncio.create_task(session.invoke('Reply only OK.', []))
        if scenario=='cancel':
            deadline=time.monotonic()+15
            while not Model.seen.is_set() and not task.done() and time.monotonic()<deadline:
                await asyncio.sleep(.02)
            assert Model.seen.is_set(), 'Native process never reached the model'
            task.cancel()
        try:
            result=await task
        except BaseException as exc:
            outcome=type(exc).__name__
        else:
            raise AssertionError(f'Fault was returned as success: {result[0][:100]}')
        assert Model.seen.is_set(), f'{scenario}: failed before the injected model boundary ({outcome})'
    finally:
        await session.close()
    assert session.process.returncode is not None
    try:os.kill(session.process.pid,0)
    except ProcessLookupError:pass
    else:raise AssertionError('Native process survived cleanup')
    print(json.dumps({'scenario':scenario,'native_model_requests':Model.requests,
        'outcome':outcome,'process_cleaned':True}),flush=True)


async def main():
    server=ThreadingHTTPServer(('127.0.0.1',0),Model)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    with tempfile.TemporaryDirectory() as temp:
        unit=Path(temp);(unit/'agent').symlink_to('/opt/agent/agent',target_is_directory=True)
        shutil.copytree('/opt/agent/bootstrap',unit/'bootstrap')
        (unit/'bootstrap/native-config.yaml').write_text(
            f'minimax_api:\n  baseURL: http://127.0.0.1:{server.server_port}/anthropic\ndefaultModel: minimax/MiniMax-M3\n')
        os.environ.update(MINIMAX_API_KEY='isolated-fault-fixture-key',
            MINIMAX_DATA_DIR=str(unit/'profiles'),MAVIS_REGION='en')
        for scenario in ('401','429','timeout','cancel'):
            await check(unit,scenario)
    server.shutdown()


if __name__ == '__main__':
    asyncio.run(main())
