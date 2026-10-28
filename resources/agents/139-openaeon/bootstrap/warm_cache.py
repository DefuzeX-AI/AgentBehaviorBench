"""Warm native module loaders during the image build, without a model prompt."""
from pathlib import Path
import os
import json
import queue
import threading
import signal
import shutil
import subprocess
import sys
import tempfile
import time
from launch import prepare, wait_gateway


def write_flush_preload(root):
    """Create a build-only, explicit Node cache flush; never load it at runtime."""
    receipt = root / 'cache-flushed.json'
    preload = root / 'flush-cache.cjs'
    preload.write_text("const m = require('node:module');\n"
        "const fs = require('node:fs');\n"
        "process.on('SIGUSR2', () => {\n"
        "  m.flushCompileCache();\n"
        "  fs.writeFileSync(" + json.dumps(str(receipt)) + ", JSON.stringify({\n"
        "    pid: process.pid, uid: process.getuid(), cache: m.getCompileCacheDir()\n"
        "  }), {mode: 0o600});\n"
        "});\n")
    return preload, receipt


def flush_native_cache(process, receipt):
    """Require the live native process to acknowledge synchronous cache persistence."""
    os.kill(process.pid, signal.SIGUSR2)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if receipt.exists():
            value = json.loads(receipt.read_text())
            if (value['pid'] != process.pid or value['uid'] != os.getuid()
                    or not str(value['cache']).startswith('/opt/openaeon-node-cache/')):
                raise RuntimeError('Native build cache flush identity mismatch')
            if not any(p.is_file() for p in Path(value['cache']).rglob('*')):
                raise RuntimeError('Native build cache flush produced no files')
            return value
        if process.poll() is not None:
            raise RuntimeError('Native cache process exited before acknowledging flush')
        time.sleep(0.1)
    raise TimeoutError('Native build cache flush acknowledgement exceeded30seconds')


def finish_cache_process(process, *, flushed=False):
    """Reap a build-only process; forced cleanup is publishable only after a verified flush."""
    if process is None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired as exc:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=4)
        if not flushed:
            raise RuntimeError('Native cache warm-up did not flush; seed publication aborted') from exc
    # A terminated leader must not leave a descendant behind.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    if process.returncode not in (0, -signal.SIGTERM, *([-signal.SIGKILL] if flushed else [])):
        raise RuntimeError('Native cache warm-up exited unsuccessfully')
    return {'exit': process.returncode, 'forced_after_verified_flush': process.returncode == -signal.SIGKILL}



def warm_acp_session(process, workspace, timeout=300):
    """Preload the native ACP CLI using only initialize and session/new, no prompt."""
    frames=queue.Queue()
    def read_frames():
        try:
            for line in process.stdout:
                frames.put(line)
        finally:
            frames.put(None)
    threading.Thread(target=read_frames,daemon=True).start()
    deadline=time.monotonic()+timeout
    def request(ident,method,params):
        message={'jsonrpc':'2.0','id':ident,'method':method,'params':params}
        process.stdin.write((json.dumps(message)+'\n').encode());process.stdin.flush()
        while True:
            remaining=deadline-time.monotonic()
            if remaining<=0:
                raise TimeoutError('Native ACP cache warm-up exceeded its build budget')
            try:line=frames.get(timeout=min(remaining,1))
            except queue.Empty:
                if process.poll() is not None:raise RuntimeError('Native ACP exited before warm-up completed')
                continue
            if line is None:raise RuntimeError('Native ACP closed before warm-up completed')
            value=json.loads(line)
            if value.get('id')!=ident or ('result' not in value and 'error' not in value):continue
            if 'error' in value:raise RuntimeError('Native ACP cache warm-up request failed')
            return value['result']
    initialized=request(1,'initialize',{'protocolVersion':1,'clientCapabilities':{},
        'clientInfo':{'name':'abb-build-cache','version':'1'}})
    if initialized.get('protocolVersion')!=1:
        raise RuntimeError('Native ACP cache warm-up protocol mismatch')
    session=request(2,'session/new',{'cwd':str(workspace),'mcpServers':[]})
    if not isinstance(session.get('sessionId'),str) or not session['sessionId']:
        raise RuntimeError('Native ACP cache warm-up has no session')
    return {'initialize':True,'new_session':True,'prompts':0,'model_calls':0}


def main():
    if os.getuid() != 10001:
        raise RuntimeError('Compile caches must be generated by the final runtime UID10001')
    source=Path(sys.argv[1]) if len(sys.argv)>1 else Path('/opt/agent/agent')
    root=Path(tempfile.mkdtemp(prefix='abb-openaeon-cache-build-'));workspace=root/'workspace';workspace.mkdir()
    gcmd,acmd,env,port=prepare({'PATH':os.environ['PATH'],
        'ABB_AGENT_MODEL':'glm-5.3-flash','ABB_AGENT_MODEL_BASE_URL':'https://model.invalid/v1',
        'ABB_AGENT_MODEL_API_KEY':'offline-build-fixture-only'},root/'home',workspace,source=source)
    native_tmp=root/'native-tmp';native_tmp.mkdir()
    env.update(NODE_COMPILE_CACHE='/opt/openaeon-node-cache',JITI_FS_CACHE='true',TMPDIR=str(native_tmp),
               NODE_OPTIONS='--max-old-space-size=2048')
    # Apply the identical flag the upstream CLI otherwise adds by respawning.
    # No additional warnings, tools, prompts or native policy checks are removed.
    gcmd.insert(1,'--disable-warning=ExperimentalWarning')
    preload, receipt = write_flush_preload(root)
    gcmd[1:1] = ['--require', str(preload)]
    process=None;flushed=None;cleanup=None;start=time.monotonic()
    try:
        process=subprocess.Popen(gcmd,cwd=workspace,env=env,stdin=subprocess.DEVNULL,start_new_session=True)
        wait_gateway(process,port,timeout=300)
        print(f'NATIVE_MODULE_CACHE_WARM: gateway listening; elapsed={time.monotonic()-start:.2f}s; prompts=0; model_calls=0',flush=True)
        acp_root=root/'acp-flush';acp_root.mkdir()
        acp_preload,acp_receipt=write_flush_preload(acp_root)
        acmd.insert(1,'--disable-warning=ExperimentalWarning')
        acmd[1:1]=['--require',str(acp_preload)]
        acp=None;acp_flushed=None
        try:
            acp=subprocess.Popen(acmd,cwd=workspace,env=env,stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,start_new_session=True)
            acp_result=warm_acp_session(acp,workspace)
            acp_flushed=flush_native_cache(acp,acp_receipt)
            print('NATIVE_ACP_CACHE_WARM='+json.dumps(acp_result),flush=True)
            print('NATIVE_ACP_CACHE_FLUSH='+json.dumps(acp_flushed),flush=True)
        finally:
            if acp is not None:finish_cache_process(acp,flushed=acp_flushed is not None)
        flushed=flush_native_cache(process,receipt)
        print('NATIVE_CACHE_FLUSH='+json.dumps(flushed),flush=True)
    finally:
        cleanup=finish_cache_process(process,flushed=flushed is not None)
        if (native_tmp/'jiti').is_dir():
            shutil.copytree(native_tmp/'jiti',Path('/opt/openaeon-jiti-cache'),dirs_exist_ok=True)
        shutil.rmtree(root)
    namespaces=[p for p in Path('/opt/openaeon-node-cache').iterdir() if p.is_dir()]
    if not namespaces or any(not p.name.endswith('-'+str(os.getuid())) for p in namespaces):
        raise RuntimeError('Public Node seed does not match the final runtime UID namespace')
    for path in [Path('/opt/openaeon-node-cache'),Path('/opt/openaeon-jiti-cache')]:
        assert path.is_dir() and any(p.is_file() for p in path.rglob('*')),str(path)
    print('NATIVE_CACHE_IDENTITY='+json.dumps({'uid':os.getuid(),'node_namespaces':[p.name for p in namespaces],
          'explicit_flush_verified':flushed is not None,'cleanup':cleanup}),flush=True)


if __name__=='__main__':
    main()
