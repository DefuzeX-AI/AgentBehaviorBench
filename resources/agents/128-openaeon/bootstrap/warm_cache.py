"""Warm native module loaders during the image build, without a model prompt."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import time
from launch import prepare, wait_gateway, stop


def main():
    source=Path(sys.argv[1]) if len(sys.argv)>1 else Path('/opt/agent/agent')
    root=Path(tempfile.mkdtemp(prefix='abb-openaeon-cache-build-'));workspace=root/'workspace';workspace.mkdir()
    gcmd,_,env,port=prepare({'PATH':os.environ['PATH'],
        'ABB_AGENT_MODEL':'glm-5.3-flash','ABB_AGENT_MODEL_BASE_URL':'https://model.invalid/v1',
        'ABB_AGENT_MODEL_API_KEY':'offline-build-fixture-only'},root/'home',workspace,source=source)
    native_tmp=root/'native-tmp';native_tmp.mkdir()
    env.update(NODE_COMPILE_CACHE='/opt/openaeon-node-cache',JITI_FS_CACHE='true',TMPDIR=str(native_tmp),
               NODE_OPTIONS='--max-old-space-size=2048')
    # Apply the identical flag the upstream CLI otherwise adds by respawning.
    # No additional warnings, tools, prompts or native policy checks are removed.
    gcmd.insert(1,'--disable-warning=ExperimentalWarning')
    process=None;start=time.monotonic()
    try:
        process=subprocess.Popen(gcmd,cwd=workspace,env=env,stdin=subprocess.DEVNULL,start_new_session=True)
        wait_gateway(process,port,timeout=300)
        print(f'NATIVE_MODULE_CACHE_WARM: gateway listening; elapsed={time.monotonic()-start:.2f}s; prompts=0; model_calls=0',flush=True)
    finally:
        stop(process)
        if (native_tmp/'jiti').is_dir():
            shutil.copytree(native_tmp/'jiti',Path('/opt/openaeon-jiti-cache'),dirs_exist_ok=True)
        shutil.rmtree(root)
    for path in [Path('/opt/openaeon-node-cache'),Path('/opt/openaeon-jiti-cache')]:
        assert path.is_dir() and any(p.is_file() for p in path.rglob('*')),str(path)


if __name__=='__main__':
    main()
