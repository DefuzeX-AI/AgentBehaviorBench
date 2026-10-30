from pathlib import Path
import importlib.util,json,os
import pytest
p=Path(__file__).resolve().parents[1]/'resources/agents/116-openaeon/bootstrap/launch.py';spec=importlib.util.spec_from_file_location('candidate_launch',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
MARK='high-risk code edit request requires explicit confirmDangerousCodeEdit=true'
def invoke(frame,pending):return m.translate_native_response((json.dumps(frame)+'\n').encode(),pending)
def test_precise_native_gate_translates_to_truthful_refusal():
 p={7:'s-7'};out=invoke({'jsonrpc':'2.0','id':7,'error':{'code':-32603,'message':'Internal error','data':{'details':MARK}}},p)
 frames=[json.loads(x) for x in out.splitlines()];assert len(frames)==2
 assert frames[0]['method']=='session/update' and frames[0]['params']['sessionId']=='s-7'
 text=frames[0]['params']['update']['content']['text'];assert MARK in text and 'adapter' in text.lower()
 assert frames[1]=={'jsonrpc':'2.0','id':7,'result':{'stopReason':'refusal'}} and 7 not in p
@pytest.mark.parametrize('frame',[{'jsonrpc':'2.0','id':7,'error':{'code':-32603,'message':'unrelated error'}},{'jsonrpc':'2.0','id':7,'result':{'stopReason':'end_turn'}},{'jsonrpc':'2.0','method':'session/update','params':{}},{'jsonrpc':'2.0','id':8,'error':{'code':-32603,'message':'Internal error','data':{'details':MARK}}},{'jsonrpc':'2.0','id':7,'error':{'code':-32602,'message':MARK}}])
def test_nonmatching_frames_are_unchanged(frame):
 b=(json.dumps(frame)+'\n').encode();assert m.translate_native_response(b,{7:'s-7'})==b

def test_malformed_output_is_unchanged():
 raw=b'not-json\n';assert m.translate_native_response(raw,{})==raw

def test_request_mapping_only_for_prompt_with_nonempty_session():
 p={};m.record_native_request(b'{"jsonrpc":"2.0","id":7,"method":"session/prompt","params":{"sessionId":"s-7"}}\n',p);assert p=={7:'s-7'}
 m.record_native_request(b'{"jsonrpc":"2.0","id":9,"method":"other","params":{"sessionId":"s9"}}\n',p);assert p=={7:'s-7'}


def test_stream_relay_keeps_request_and_other_response_bytes():
 import io,threading
 request=b'{"jsonrpc":"2.0","id":4,"method":"session/prompt","params":{"sessionId":"s"}}\n'; pending={}; lock=threading.Lock()
 class Destination(io.BytesIO):
  def close(self):pass
 import os
 r,w=os.pipe();os.write(w,request);os.close(w)
 dest=Destination();m.relay_native_input(r,dest,pending,lock);os.close(r);assert dest.getvalue()==request and pending=={4:'s'}
 native=b'{"jsonrpc":"2.0","id":4,"result":{"stopReason":"end_turn"}}\n';out=io.BytesIO();m.relay_native_output(io.BytesIO(native),out,pending,lock);assert out.getvalue()==native and pending=={}

def test_closed_prompt_cannot_map_a_later_reused_id():
 pending={7:'s'};invoke({'jsonrpc':'2.0','id':7,'result':{'stopReason':'end_turn'}},pending);assert not pending
 frame={'jsonrpc':'2.0','id':7,'error':{'code':-32603,'message':'Internal error','data':{'details':MARK}}};assert invoke(frame,pending)==(json.dumps(frame)+'\n').encode()


def test_server_request_reusing_prompt_id_does_not_consume_pending_prompt():
 pending={7:'s-7'}
 frame={'jsonrpc':'2.0','id':7,'method':'session/request_permission','params':{'sessionId':'s-7'}}
 data=(json.dumps(frame)+'\n').encode();assert m.translate_native_response(data,pending)==data;assert pending=={7:'s-7'}
 risk={'jsonrpc':'2.0','id':7,'error':{'code':-32603,'message':'Internal error','data':{'details':MARK}}}
 assert json.loads(invoke(risk,pending).splitlines()[-1])['result']['stopReason']=='refusal'


def test_idle_open_stdin_does_not_crash_interpreter_shutdown():
 import subprocess,sys
 code="import importlib.util,threading,time,sys; s=importlib.util.spec_from_file_location('l',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m); d=open('/dev/null','wb');threading.Thread(target=m.relay_native_input,args=(sys.stdin.fileno(),d,{},threading.Lock()),daemon=True).start();time.sleep(.2)"
 p=subprocess.Popen([sys.executable,'-c',code,m.__file__],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 try:
  assert p.wait(timeout=4)==0
  assert b'Fatal Python error' not in p.stderr.read()
 finally:
  if p.poll() is None:p.kill();p.wait()
  p.stdin.close()


def test_main_uses_raw_stdin_fd_not_a_buffered_daemon_reader():
 import inspect
 source=inspect.getsource(m.main);assert 'sys.stdin.fileno()' in source and 'args=(sys.stdin.buffer,' not in source
