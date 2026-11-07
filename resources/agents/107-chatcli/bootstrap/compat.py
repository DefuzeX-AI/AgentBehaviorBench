"""ABB-only, reversible OpenAI tool-name transport. Native ChatCLI is unchanged.

All tools remain present. Only the three pinned cmd:* metadata names are aliased.
A response is buffered per model call to reconstruct fragmented SSE tool names;
arguments, content, event order, status and model selection are not replaced.
"""
from __future__ import annotations
import copy
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ALIASES = {"cmd:help": "cmd_help", "cmd:session-list": "cmd_session-list", "cmd:version": "cmd_version"}
REVERSE = {v:k for k,v in ALIASES.items()}
VALID = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
LIMIT = 32 * 1024 * 1024

def _out(name):
    value = ALIASES.get(name, name)
    if not isinstance(value,str) or not VALID.fullmatch(value):
        raise ValueError("Unsupported non-OpenAI tool name")
    return value

def outgoing(body):
    """Map declarations, forced choices and conversation history coherently."""
    value = copy.deepcopy(body)
    names=[t['function']['name'] for t in value.get('tools',[]) if t.get('type')=='function']
    mapped=[_out(n) for n in names]
    if len(set(mapped)) != len(mapped):raise ValueError('Tool alias collision')
    for t in value.get('tools',[]):
        if t.get('type')=='function':t['function']['name']=_out(t['function']['name'])
    for f in value.get('functions',[]):f['name']=_out(f['name'])
    choice=value.get('tool_choice')
    if isinstance(choice,dict) and isinstance(choice.get('function'),dict):choice['function']['name']=_out(choice['function']['name'])
    choice=value.get('function_call')
    if isinstance(choice,dict) and 'name' in choice:choice['name']=_out(choice['name'])
    for m in value.get('messages',[]):
        for t in m.get('tool_calls',[]):
            if isinstance(t.get('function'),dict) and 'name' in t['function']:t['function']['name']=_out(t['function']['name'])
        if isinstance(m.get('function_call'),dict) and 'name' in m['function_call']:m['function_call']['name']=_out(m['function_call']['name'])
        if m.get('role') in ('tool','function') and 'name' in m:m['name']=_out(m['name'])
    return value

def incoming(body):
    value=copy.deepcopy(body)
    for c in value.get('choices',[]):
        for key in ('message','delta'):
            m=c.get(key) or {}
            for t in m.get('tool_calls',[]):
                f=t.get('function') or {}
                if 'name' in f:f['name']=REVERSE.get(f['name'],f['name'])
            f=m.get('function_call')
            if isinstance(f,dict) and 'name' in f:f['name']=REVERSE.get(f['name'],f['name'])
    return value

def incoming_sse(raw):
    """Keep every SSE frame; reconstruct names only, not tool arguments/content."""
    text=raw.decode('utf-8');lines=text.splitlines(keepends=True);records=[];locations={}
    for i,line in enumerate(lines):
        if not line.startswith('data:'):continue
        data=line[5:].strip()
        if data=='[DONE]':continue
        value=json.loads(data);records.append((i,value))
        for choice in value.get('choices',[]):
            delta=choice.get('delta') or {};ci=choice.get('index',0)
            for t in delta.get('tool_calls',[]):
                f=t.get('function') or {}
                if 'name' in f:locations.setdefault((ci,'tool',t.get('index',0)),[]).append(f)
            f=delta.get('function_call')
            if isinstance(f,dict) and 'name' in f:locations.setdefault((ci,'legacy',0),[]).append(f)
    for fragments in locations.values():
        whole=''.join(f['name'] for f in fragments)
        if whole in REVERSE:
            fragments[0]['name']=REVERSE[whole]
            for f in fragments[1:]:f['name']=''
    for i,value in records:
        ending='\r\n' if lines[i].endswith('\r\n') else '\n' if lines[i].endswith('\n') else ''
        lines[i]='data: '+json.dumps(value,ensure_ascii=False,separators=(',',':'))+ending
    return ''.join(lines).encode('utf-8')

def serve(upstream,timeout=900):
    """Loopback-only relay to ABB's selected/intercepted upstream, never fallback."""
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            if self.path!='/chat/completions':self.send_error(404);return
            try:
                n=int(self.headers.get('Content-Length','0'))
                if not 0<n<=LIMIT:raise ValueError('Invalid request length')
                body=outgoing(json.loads(self.rfile.read(n)))
                skip={'host','connection','transfer-encoding','content-length','accept-encoding'}
                headers={k:v for k,v in self.headers.items() if k.lower() not in skip}
                headers['Accept-Encoding']='identity'
                request=Request(upstream,json.dumps(body,ensure_ascii=False,separators=(',',':')).encode(),headers,method='POST')
                try:response=urlopen(request,timeout=timeout)
                except HTTPError as error:response=error
                with response:
                    raw=response.read(LIMIT+1)
                    if len(raw)>LIMIT:raise ValueError('Model response exceeds explicit transport bound')
                    status=response.code;ctype=response.headers.get('Content-Type','')
                    if 200<=status<300:
                        raw=incoming_sse(raw) if 'text/event-stream' in ctype else json.dumps(incoming(json.loads(raw)),ensure_ascii=False,separators=(',',':')).encode()
                    self.send_response(status)
                    for k,v in response.headers.items():
                        if k.lower() not in {'content-length','transfer-encoding','connection','content-encoding'}:self.send_header(k,v)
                    self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
            except (ValueError,KeyError,TypeError,json.JSONDecodeError):
                self.send_error(422,'Invalid tool transport payload')
            except Exception:
                self.send_error(502,'Selected upstream transport failed')
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    return server,'http://127.0.0.1:'+str(server.server_port)+'/chat/completions'
