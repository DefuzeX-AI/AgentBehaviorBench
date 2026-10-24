"""Protocol fixtures, not real Agent acceptance or model responses."""
from pathlib import Path
import importlib.util
import json
import copy
import pytest

PATH=Path(__file__).resolve().parents[1]/'resources/agents/105-chatcli/bootstrap/compat.py'
def module():
    spec=importlib.util.spec_from_file_location('chatcli_transport',PATH)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def payload():
    names=['coder','cmd:help','cmd:session-list','cmd:version']
    return {'model':'glm-5.3-flash','messages':[{'role':'user','content':'Do not change cmd:help inside text.'},
        {'role':'assistant','tool_calls':[{'id':'call-1','type':'function','function':{'name':'cmd:help','arguments':'{"x":"cmd:help"}'}}]},
        {'role':'tool','tool_call_id':'call-1','name':'cmd:help','content':'native result stays exact'}],
        'tool_choice':{'type':'function','function':{'name':'cmd:version'}},
        'tools':[{'type':'function','function':{'name':n,'description':'unchanged','parameters':{'type':'object'}}} for n in names]}

def test_all_tools_remain_with_strict_names_and_exact_arguments():
    m=module();p=payload();before=copy.deepcopy(p);q=m.outgoing(p)
    assert p==before and len(q['tools'])==len(p['tools'])==4
    assert [t['function']['name'] for t in q['tools']]==['coder','cmd_help','cmd_session-list','cmd_version']
    assert all(m.VALID.fullmatch(t['function']['name']) for t in q['tools'])
    assert q['model']==p['model'] and q['messages'][0]==p['messages'][0]
    assert q['messages'][1]['tool_calls'][0]['function']=={'name':'cmd_help','arguments':'{"x":"cmd:help"}'}
    assert q['messages'][2]['name']=='cmd_help' and q['messages'][2]['content']=='native result stays exact'
    assert q['tool_choice']['function']['name']=='cmd_version'

@pytest.mark.parametrize('bad',['unknown:tool','space name','a'*65,'@unexpected',''])
def test_unhandled_invalid_names_fail_before_network(bad):
    m=module();p=payload();p['tools'][0]['function']['name']=bad
    with pytest.raises(ValueError,match='Unsupported'):m.outgoing(p)

def test_alias_collision_fails_before_model():
    m=module();p=payload();p['tools'][0]['function']['name']='cmd_help'
    with pytest.raises(ValueError,match='collision'):m.outgoing(p)

def test_nonstream_response_restores_only_names():
    m=module();p={'model':'glm-5.3-flash','usage':{'total_tokens':7},'choices':[{'message':{'content':'cmd_help is literal text','tool_calls':[{'id':'x','function':{'name':'cmd_help','arguments':'{"key":"cmd_help"}'}}]},'finish_reason':'tool_calls'}]};before=copy.deepcopy(p);q=m.incoming(p)
    assert p==before
    assert q['choices'][0]['message']['tool_calls'][0]['function']['name']=='cmd:help'
    q['choices'][0]['message']['tool_calls'][0]['function']['name']='cmd_help'
    assert q==p

@pytest.mark.parametrize('name,parts',[('cmd_help',['cmd_','he','lp']),('cmd_session-list',['cmd_session','-list']),('cmd_version',['cmd_version'])])
def test_fragmented_sse_preserves_arguments_content_ids_order(name,parts):
    m=module();rows=[]
    for i,part in enumerate(parts):
        rows.append({'id':'same','choices':[{'index':0,'delta':{'content':'text'+str(i),'tool_calls':[{'index':0,'id':'x' if i==0 else '', 'function':{'name':part,'arguments':['{"a":','1','}'][i] if i<3 else ''}}]}}]})
    raw=': keepalive\n\n'+''.join('data: '+json.dumps(r)+'\n\n' for r in rows)+'data: [DONE]\n\n'
    restored=m.incoming_sse(raw.encode()).decode();out=[json.loads(l[5:].strip()) for l in restored.splitlines() if l.startswith('data:') and l.strip()!='data: [DONE]']
    assert restored.startswith(': keepalive\n\n') and restored.endswith('data: [DONE]\n\n') and len(out)==len(rows)
    assert ''.join(x['choices'][0]['delta']['tool_calls'][0]['function']['name'] for x in out)==m.REVERSE[name]
    for a,b in zip(out,rows):
        a['choices'][0]['delta']['tool_calls'][0]['function']['name']=b['choices'][0]['delta']['tool_calls'][0]['function']['name']
        assert a==b

def test_multiple_streamed_calls_are_not_conflated():
    m=module();d={'choices':[{'index':0,'delta':{'tool_calls':[{'index':0,'function':{'name':'cmd_help','arguments':'{}'}},{'index':1,'function':{'name':'cmd_version','arguments':'{}'}}]}}]}
    raw=('data: '+json.dumps(d)+'\n\ndata: [DONE]\n\n').encode();out=m.incoming_sse(raw).decode();v=json.loads(out.splitlines()[0][5:]);assert [x['function']['name'] for x in v['choices'][0]['delta']['tool_calls']]==['cmd:help','cmd:version']

def test_legacy_function_fields_roundtrip():
    m=module();p={'functions':[{'name':'cmd:help'}],'function_call':{'name':'cmd:help'},'messages':[{'function_call':{'name':'cmd:help','arguments':'{}'}}]};q=m.outgoing(p);assert q['functions'][0]['name']=='cmd_help' and q['function_call']['name']=='cmd_help';r=m.incoming({'choices':[{'message':{'function_call':{'name':'cmd_help','arguments':'{}'}}}]});assert r['choices'][0]['message']['function_call']['name']=='cmd:help'

def test_real_http_relay_forwards_auth_body_and_upstream_error_without_fabrication():
    from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
    from threading import Thread
    from urllib.request import Request,urlopen
    from urllib.error import HTTPError
    m=module();seen=[]
    class Upstream(BaseHTTPRequestHandler):
        def log_message(self,*a):pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));seen.append((body,self.headers.get('Authorization')))
            assert all(m.VALID.fullmatch(t['function']['name']) for t in body['tools'])
            raw=b'{"error":{"message":"fixture upstream rate limit"}}';self.send_response(429);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    upstream=ThreadingHTTPServer(('127.0.0.1',0),Upstream);Thread(target=upstream.serve_forever,daemon=True).start();relay,url=m.serve(f'http://127.0.0.1:{upstream.server_port}/v1/chat/completions',timeout=5)
    try:
        with pytest.raises(HTTPError) as exc:urlopen(Request(url,json.dumps(payload()).encode(),{'Content-Type':'application/json','Authorization':'Bearer fixture-only'}),timeout=10)
        assert exc.value.code==429 and exc.value.read()==b'{"error":{"message":"fixture upstream rate limit"}}'
        assert len(seen)==1 and seen[0][1]=='Bearer fixture-only' and len(seen[0][0]['tools'])==4
    finally:relay.shutdown();relay.server_close();upstream.shutdown();upstream.server_close()
