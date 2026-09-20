"""Real native ACP: delay title into turn two, preserving session-only ownership."""
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
    title_started = threading.Event()
    second_started = threading.Event()
    requests = []
    def log_message(self,*args):pass
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers.get('content-length','0'))))
        if 'count_tokens' in self.path or 'input_tokens' in self.path:
            data=b'{"input_tokens":10}';self.send_response(200)
            self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)))
            self.end_headers();self.wfile.write(data);return
        title=any(t.get('name')=='submit_session_title' for t in body.get('tools',[]))
        kind='title' if title else 'agent'
        identifier=f'msg-{kind}-{sum(r["kind"]==kind for r in self.requests)+1}'
        self.requests.append({'id':identifier,'kind':kind,'session':self.headers.get('X-Mavis-Session-Id')})
        if title:
            self.title_started.set()
            if not self.second_started.wait(8):raise AssertionError('Next foreground turn did not overlap title')
            time.sleep(.3)
        elif sum(r['kind']=='agent' for r in self.requests)==2:
            self.second_started.set()
        content=({'type':'tool_use','id':identifier+'-tool','name':'submit_session_title','input':{}} if title
                 else {'type':'text','text':''})
        delta=({'type':'input_json_delta','partial_json':'{"title":"Fixture"}'} if title
               else {'type':'text_delta','text':'OK'})
        frames=[{'type':'message_start','message':{'id':identifier,'type':'message','role':'assistant',
            'model':'MiniMax-M3','content':[],'stop_reason':None,'usage':{'input_tokens':10,'output_tokens':1}}},
            {'type':'content_block_start','index':0,'content_block':content},
            {'type':'content_block_delta','index':0,'delta':delta},{'type':'content_block_stop','index':0},
            {'type':'message_delta','delta':{'stop_reason':'tool_use' if title else 'end_turn'},'usage':{'output_tokens':2}},
            {'type':'message_stop'}]
        data=''.join('event: '+f['type']+'\ndata: '+json.dumps(f)+'\n\n' for f in frames).encode()
        self.send_response(200);self.send_header('Content-Type','text/event-stream')
        self.send_header('Content-Length',str(len(data)));self.end_headers()
        try:self.wfile.write(data)
        except (BrokenPipeError,ConnectionResetError):pass


class Evidence:
    def __init__(self):self.calls=[]
    def on_acp_event(self,name,data):
        if name=='native_model_call':self.calls.append(data)


async def main():
    server=ThreadingHTTPServer(('127.0.0.1',0),Model)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    with tempfile.TemporaryDirectory() as temp:
        unit=Path(temp);(unit/'agent').symlink_to('/opt/agent/agent',target_is_directory=True)
        shutil.copytree('/opt/agent/bootstrap',unit/'bootstrap')
        (unit/'bootstrap/native-config.yaml').write_text(
            f'minimax_api:\n  baseURL: http://127.0.0.1:{server.server_port}/anthropic\ndefaultModel: minimax/MiniMax-M3\n')
        os.environ.update(MINIMAX_API_KEY='isolated-title-fixture-key',MINIMAX_DATA_DIR=str(unit/'profiles'),MAVIS_REGION='en')
        session=ACPSession(ACPConfig(unit,('python',str(unit/'bootstrap/launch.py')),'/home/agent/workspace',
            env_keys=('MINIMAX_API_KEY','MINIMAX_DATA_DIR','MAVIS_REGION'),timeout=15,handshake_timeout=10,
            cleanup_timeout=1,evidence_reader='bootstrap/native_evidence.py:read_calls'))
        first,second=Evidence(),Evidence()
        try:
            await session.invoke('Reply only OK without tools.',[first])
            deadline=time.monotonic()+5
            while not Model.title_started.is_set() and time.monotonic()<deadline:await asyncio.sleep(.02)
            assert Model.title_started.is_set(),'No native title call observed'
            await session.invoke('Reply only OK again without tools.',[second])
            assert [c['native_response_id'] for c in first.calls]==['msg-agent-1']
            assert [c['native_response_id'] for c in second.calls]==['msg-agent-2']
            assert first.calls[0]['native_turn_id']!=second.calls[0]['native_turn_id']
            assert len({r['session'] for r in Model.requests})==1
            assert Model.second_started.is_set()
            print(json.dumps({'status':'passed','delayed_title_overlapped_turn_2':True,
                'foreground_inputs_linked':2,'background_assigned_to_current_input':False,
                'native_session_header_preserved':True,'requests':Model.requests}),flush=True)
        finally:await session.close()
    server.shutdown()


if __name__ == '__main__':
    asyncio.run(main())
