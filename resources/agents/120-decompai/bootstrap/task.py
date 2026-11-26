"""Use original Gradio callbacks and real binary analysis on an isolated Docker backend."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, '/opt/agent/agent')

request = json.loads(Path(sys.argv[1]).read_text())
work = Path(request['workspace'])
ready = Path('/workspace/.decomp-docker/ready.json')
for _ in range(540):
    if ready.exists():
        break
    time.sleep(1)
else:
    raise RuntimeError('The isolated native Docker backend was not provisioned')
backend = json.loads(ready.read_text())
os.environ.update(
    DOCKER_HOST=backend['host'], DOCKER_TLS_VERIFY='1', DOCKER_CERT_PATH='/workspace/.decomp-docker',
    DECOMPAI_RUNNER_IMAGE=backend['image'], DECOMPAI_RUNNER_BUILD='false',
    ANALYSIS_SESSIONS_ROOT=str(work/'sessions'), DECOMPAI_SESSIONS_HOST_DIR=str(work/'sessions'),
    DECOMPAI_BINARIES_HOST_DIR=str(work/'binaries'), DECOMPAI_SOURCE_HOST_DIR=str(work/'source_code'),
    OPENAI_API_KEY=os.environ['ABB_AGENT_MODEL_API_KEY'],
    OPENAI_BASE_URL=os.environ['ABB_AGENT_MODEL_BASE_URL'], LLM_MODEL=os.environ['ABB_AGENT_MODEL'],
)
for name in ('sessions','binaries','source_code'):
    (work/name).mkdir()
source = work/'source_code/hello.c'
source.write_text('#include <stdio.h>\nint main(void) { puts("hello"); return 0; }\n')
binary = work/'binaries/hello'
subprocess.run(['docker','run','--rm','--platform','linux/amd64',
    '--mount',f'type=bind,source={source.parent},target=/source_code,readonly',
    '--mount',f'type=bind,source={binary.parent},target=/binaries',
    backend['image'],'gcc','-O0','-g','/source_code/hello.c','-o','/binaries/hello'],check=True)
import gradio as gr
from src import main
with gr.Blocks(css=main.CSS, title='Binary Analysis Agent') as demo:
    main.demo_block()
functions = {fn.fn.__name__:fn.fn for fn in demo.fns.values() if fn.fn is not None}
for endpoint in demo.fns.values():
    owner = getattr(endpoint.fn, '__self__', None)
    callback = getattr(owner, 'fn', None)
    if callback is not None and getattr(callback, '__name__', '') == 'process_request':
        functions['process_request'] = callback
start = functions['start_session']
process = functions['process_request']
state, history, _ = start(str(binary), [], None)
# The native callback must have completed genuine disassembly before chatting.
assembly = Path(state['disassembled_path']).read_text()
if not assembly.strip() or 'file format' not in assembly:
    raise RuntimeError('Native initial disassembly did not produce assembly evidence')

async def run():
    final = None
    async for update in process(request['text'], history, state, None):
        final = update
    if final is None:
        raise RuntimeError('Native conversation returned no updates')
    messages, _, session = final
    return {'native_mode':'binary_analysis','binary':str(binary),'session_id':session,
            'messages':[m if isinstance(m,dict) else vars(m) for m in messages]}
result = asyncio.run(run())
Path(sys.argv[2]).write_text(json.dumps(result,ensure_ascii=False,default=str))
