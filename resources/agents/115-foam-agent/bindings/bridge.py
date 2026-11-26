"""Execute the native OpenFOAM workflow, preserving preparation, review and tools."""
import os
from pathlib import Path
import subprocess
import sys


class NativeBinding:
    def invoke(self, value, config=None, **kwargs):
        from config import Config
        from main import main, workflow_exit_code
        text = value['message'] if isinstance(value, dict) else value
        deployment = Config(model_provider='openai', model_version='gpt-4o-mini',
                            run_directory=str(Path.home()/'foam-runs'))
        state = main(text, deployment)
        if workflow_exit_code(state):
            raise RuntimeError(f'Native Foam-Agent workflow stopped: {state.get("termination_reason") or state.get("workflow_status")}')
        # Report actual native workflow outputs, not a synthetic chat reply.
        fields = ('workflow_status', 'case_info', 'case_name', 'case_dir',
                  'mesh_review_history', 'solver_review_history',
                  'solver_execution', 'mesh_execution', 'final_reconstruction')
        return {key: state.get(key) for key in fields if key in state}


def create_graph():
    # Use the upstream runtime initializer to load OpenFOAM/Conda and bundled
    # model paths; environment values are consumed in memory, never logged.
    raw = subprocess.check_output(['/usr/local/bin/foamagent-entrypoint.sh', 'env', '-0'])
    for pair in raw.split(b'\0'):
        if b'=' in pair:
            key, value = pair.split(b'=', 1)
            os.environ[key.decode()] = value.decode()
    sys.path.insert(0, '/home/openfoam/Foam-Agent/src')
    os.chdir('/home/openfoam/Foam-Agent')
    return NativeBinding()
