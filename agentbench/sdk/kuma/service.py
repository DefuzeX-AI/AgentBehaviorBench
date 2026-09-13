"""Host orchestration using the existing Docker runtime and network isolation."""
import json
import shutil
from pathlib import Path
from uuid import uuid4
from agentbench.runtime.docker import DockerRuntime
from agentbench.runtime.docker.policy import DockerPolicy
from agentbench.observe.store import TraceStore
from agentbench.sdk.common.artifacts import Artifacts
from .image import evaluation_agent
from agentbench.runtime.docker.worker_build import _ignore


class EvaluationPolicy:
    def __init__(self, state):
        self.state = state.resolve()

    def run_arguments(self):
        return (*DockerPolicy().run_arguments(), '--mount',
                f'type=bind,source={self.state.parent},target=/opt/agent/agent,readonly', '--mount',
                f'type=bind,source={self.state},target=/opt/agent/agent/.kuma')


def evaluate(agent, *, output, sdk, environ, timeout=2400, trace_sink=None, trace_max_bytes=262144,
             on_artifacts_ready=None, max_steps=None, excluded_cases=(),
             generation_count=None, case_artifact=None):
    if not (environ.get('KUMA_API_KEY') or environ.get('DEFUZEX_API_KEY')):
        raise ValueError('KUMA_API_KEY or DEFUZEX_API_KEY is required')
    directory = output.resolve() / uuid4().hex
    directory.mkdir(parents=True, mode=0o700)
    files = Artifacts(directory)
    inputs = directory / 'request'; inputs.mkdir()
    # The Case artifact is addressed inside the Run repository; the host copies the
    # prepared file into the repository ledger below, before the container starts.
    reused = f'.kuma/{Path(case_artifact).name}' if case_artifact is not None else None
    files.save('request/evaluation.json', {
        'max_steps': max_steps, 'excluded_cases': list(excluded_cases),
        'mode': 'generate' if generation_count is not None else 'execute',
        'count': generation_count, 'case_artifact': reused})
    destination = directory / 'evaluation'; destination.mkdir(mode=0o777); destination.chmod(0o777)
    status = {'schema': 'abb.evaluate.run.v1', 'run_id': directory.name,
              'agent_id': agent.agent_id, 'status': 'running'}
    files.save('run.json', status)
    print(f'Run: {directory.name}\nArtifacts: {directory}', flush=True)
    session = None
    try:
        if on_artifacts_ready is not None:
            on_artifacts_ready(directory)
        with evaluation_agent(agent, sdk) as descriptor:
            # SDK requires repo and its ledger on the same filesystem. Mount the
            # actual staged Agent source read-only, with only its .kuma writable.
            repository = directory / 'sdk-repo'
            shutil.copytree(descriptor.path / 'agent', repository, ignore=_ignore)
            state = repository / '.kuma'; state.mkdir(mode=0o777); state.chmod(0o777)
            if case_artifact is not None:
                shutil.copyfile(case_artifact, state / Path(case_artifact).name)
            store = TraceStore(directory / 'network.jsonl', directory.name, source='interceptor')
            class Sink:
                def emit(self, event):
                    store.emit(event)
                    if trace_sink is not None:
                        trace_sink.emit(event)
            runtime = DockerRuntime(environ=environ, policy=EvaluationPolicy(state), trace_sink=Sink(),
                                    trace_max_bytes=trace_max_bytes)
            session = runtime.start(descriptor, invocation=(inputs, destination))
            checkpoint = session.trace_checkpoint()
            code = session.wait(timeout=timeout)
            status['exit_code'] = code
            # Preparation calls the SDK only; no Agent/LLM invocation exists.
            if code == 0 and generation_count is None:
                session.validate_trace(checkpoint)
            status['status'] = 'succeeded' if code == 0 else 'failed'
    except BaseException as exc:
        status.update(status='failed', error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        if session is not None:
            session.close()
            files.save('diagnostics.json', {'stdout': session.stdout, 'stderr': session.stderr})
        files.save('run.json', status)
    print(f'Status: {status["status"]}', flush=True)
    return directory
