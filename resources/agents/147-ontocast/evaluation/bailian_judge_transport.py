"""Single-call Judge relay: preserve evidence and enforce supported JSON shape."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json, threading, time, urllib.request, urllib.error

MODEL = 'qwen3.7-max-2026-06-08'
schema = {'type':'object', 'properties':{
    'status':{'type':'string','enum':['pass','issue','inconclusive']},
    'confidence':{'type':'string','enum':['low','medium','high']},
    'reason':{'type':'string'},
    'issues':{'type':'array','items':{'type':'object','properties':{'input_id':{'type':'string'},'message':{'type':'string'}},'required':['input_id','message'],'additionalProperties':False}},
    'evidence_gaps':{'type':'array','items':{'type':'string'}}},
    'required':['status','confidence','reason','issues','evidence_gaps'],'additionalProperties':False}

class BailianJudgeTransport:
    def __init__(self, record):
        self.record, self.calls, self.lock = record, [], threading.Lock()
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                if self.path != '/v1/chat/completions': self.send_error(404); return
                raw_body = self.rfile.read(int(self.headers['Content-Length']))
                try: body = json.loads(raw_body)
                except ValueError: self.send_error(400); return
                if body.get('model') != MODEL or body.get('stream') or len(raw_body)>6000000:
                    self.send_error(400); return
                with owner.lock:
                    if owner.calls: self.send_error(400, 'Single request guard'); return
                    entry={'model':MODEL,'input_bytes':len(raw_body),'max_tokens':body.get('max_tokens'),
                           'thinking':False,'response_format':'strict json_schema',
                           'scope':'Judge only; original messages retained'}
                    owner.calls.append(entry)
                body['enable_thinking'] = False
                body['response_format'] = {'type':'json_schema','json_schema':{'name':'abb_judge','strict':True,'schema':schema}}
                request=urllib.request.Request('https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions',
                    json.dumps(body).encode(),headers={'Content-Type':'application/json','Authorization':self.headers.get('Authorization','')})
                started=time.monotonic()
                try:
                    with urllib.request.urlopen(request,timeout=240) as response: raw=response.read(); status=response.status
                    reply=json.loads(raw)
                    entry.update(status=status,usage=reply.get('usage'),finish_reasons=[c.get('finish_reason') for c in reply.get('choices',[])])
                except urllib.error.HTTPError as error:
                    status=error.code; raw=error.read(); entry.update(status=status)
                except Exception as error:
                    status=502; raw=b'{"error":"Judge upstream request failed"}'; entry.update(status=status,error_type=type(error).__name__)
                finally:
                    entry['seconds']=round(time.monotonic()-started,2)
                    owner.record.write_text(json.dumps({'purpose':'Single Judge request; evidence and model response unchanged','calls':owner.calls},indent=2)+'\n')
                self.send_response(status); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(raw))); self.end_headers()
                try:self.wfile.write(raw)
                except BrokenPipeError:pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
    def start(self): self.thread.start(); return 'http://127.0.0.1:'+str(self.server.server_port)+'/v1'
    def close(self): self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=5)
