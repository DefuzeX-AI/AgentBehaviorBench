"""Exercise the native WebQA CLI against a real isolated local greeting page."""
import asyncio
import functools
import http.server
import io
import json
import os
from pathlib import Path
import sys
import threading

request = json.loads(Path(sys.argv[1]).read_text())
work = Path(request['workspace'])
site = work/'site'
site.mkdir()
(site/'index.html').write_text('<!doctype html><html lang="zh"><meta charset="utf-8"><title>Greeting test</title><main><h1>你好</h1><p>A local browser smoke-test page.</p></main></html>')
server = http.server.ThreadingHTTPServer(('127.0.0.1', 8787),
    functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(site)))
threading.Thread(target=server.serve_forever, daemon=True).start()
os.environ['DOCKER_ENV'] = 'true'
os.chdir(work)
from webqa_agent.cli import execute_gen_mode

config = {
    'engine': 'flash',
    'target': {'url': 'http://127.0.0.1:8787', 'max_concurrent_tests': 1},
    'test_config': {'business_objectives': request['text']},
    'llm_config': {'api': 'openai', 'model': os.environ['ABB_AGENT_MODEL'],
        'filter_model': os.environ['ABB_AGENT_MODEL'],
        'api_key': os.environ['ABB_AGENT_MODEL_API_KEY'],
        'base_url': os.environ['ABB_AGENT_MODEL_BASE_URL']},
    'browser_config': {'headless': True},
}
output = io.StringIO()
original = sys.stdout
class Tee:
    def write(self, text):
        output.write(text)
        return original.write(text)
    def flush(self):
        original.flush()
sys.stdout = Tee()
try:
    asyncio.run(execute_gen_mode(config, workers=1))
finally:
    sys.stdout = original
    server.shutdown()
    server.server_close()
Path(sys.argv[2]).write_text(json.dumps({'native_mode': 'flash',
    'target': 'http://127.0.0.1:8787', 'native_output': output.getvalue()}, ensure_ascii=False))
