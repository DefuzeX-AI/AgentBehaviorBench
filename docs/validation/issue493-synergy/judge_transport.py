"""Host-only transport for an unchanged ABB local Judge, using non-thinking DS.

The original Judge messages and response bytes pass through unchanged. Only the
provider's documented thinking option is supplied; this never handles Agent traffic.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json, threading, urllib.request, urllib.error

class JudgeTransport:
    def __init__(self, base_url, record):
        self.base_url=base_url.rstrip('/')
        self.record=record
        self.calls=[]
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_POST(self):
                if self.path!='/v1/chat/completions': self.send_error(404);return
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if body.get('model')!='deepseek-flash' or body.get('stream') or len(owner.calls)>=3:
                    self.send_error(400);return
                body['thinking']={'type':'disabled'}
                entry={'model':body['model'],'thinking':body['thinking'],'max_tokens':body.get('max_tokens'),'purpose':'ABB local Judge only; original messages retained'}
                owner.calls.append(entry)
                request=urllib.request.Request(owner.base_url+'/chat/completions',json.dumps(body).encode(),headers={'content-type':'application/json','authorization':self.headers.get('Authorization','')})
                try:
                    with urllib.request.urlopen(request,timeout=180) as response:
                        raw=response.read();status=response.status
                    parsed=json.loads(raw)
                    entry.update(status=status,usage=parsed.get('usage'),finish_reasons=[c.get('finish_reason') for c in parsed.get('choices',[])])
                except urllib.error.HTTPError as error:
                    status=error.code;raw=error.read();entry.update(status=status)
                except Exception as error:
                    status=502;raw=json.dumps({'error':'Judge transport upstream request failed'}).encode();entry.update(status=status,error_type=type(error).__name__)
                finally:
                    owner.record.write_text(json.dumps({'purpose':'Judge-only non-thinking transport; no response rewriting','requests':owner.calls},indent=2))
                self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
    def start(self): self.thread.start();return 'http://127.0.0.1:'+str(self.server.server_port)+'/v1'
    def close(self): self.server.shutdown();self.server.server_close();self.thread.join(timeout=5)
