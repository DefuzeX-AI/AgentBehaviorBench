import importlib.util,os,sys,subprocess,json
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
bootstrap=ROOT/'resources/agents/139-openaeon/bootstrap'
launch=Path(os.environ.get('TEST_LAUNCH',str(bootstrap/'launch.py')))
warm=Path(os.environ.get('TEST_WARM',str(bootstrap/'warm_cache.py')))
spec=importlib.util.spec_from_file_location('warm_candidate',warm)
m=importlib.util.module_from_spec(spec)
sys.path.insert(0,str(launch.parent))
spec.loader.exec_module(m)
SERVER=r'''
import sys,json
mode=sys.argv[1]
for line in sys.stdin:
 v=json.loads(line);method=v['method'];ident=v['id']
 if method not in ('initialize','session/new'):raise SystemExit(6)
 if mode=='error':print(json.dumps({'jsonrpc':'2.0','id':ident,'error':{'code':-32603}}),flush=True);continue
 result={'protocolVersion':1} if method=='initialize' else {'sessionId':'native-id'}
 if mode=='badprotocol' and method=='initialize':result={'protocolVersion':99}
 if mode=='badsession' and method=='session/new':result={'sessionId':''}
 print(json.dumps({'jsonrpc':'2.0','id':ident,'result':result}),flush=True)
'''
def spawn(mode):return subprocess.Popen([sys.executable,'-u','-c',SERVER,mode],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
def test_initialize_and_new_session_no_prompt(tmp_path):
 p=spawn('ok')
 try:assert m.warm_acp_session(p,tmp_path,timeout=5)=={'initialize':True,'new_session':True,'prompts':0,'model_calls':0}
 finally:p.terminate();p.wait(timeout=5)
@pytest.mark.parametrize('mode',['error','badprotocol','badsession'])
def test_fail_closed_invalid_handshake(tmp_path,mode):
 p=spawn(mode)
 try:
  with pytest.raises(RuntimeError):m.warm_acp_session(p,tmp_path,timeout=5)
 finally:p.terminate();p.wait(timeout=5)
def test_timeout_does_not_change_native_timeout(tmp_path):
 p=subprocess.Popen([sys.executable,'-u','-c','import time;time.sleep(10)'],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
 try:
  with pytest.raises(TimeoutError):m.warm_acp_session(p,tmp_path,timeout=0.1)
 finally:p.terminate();p.wait(timeout=5)
