"""Host orchestration using the existing Docker runtime and network isolation."""
import json
import shutil
from collections.abc import Mapping
from pathlib import Path
from uuid import uuid4
from agentbench.runtime.docker import DockerRuntime
from agentbench.runtime.docker.policy import DockerPolicy
from agentbench.runtime.contracts.execution import (
    Deadline, DockerCleanupError, RunCancelled, RunControl, RuntimeLimits,
)
from agentbench.runtime.interception import TraceEvent
from agentbench.observe.store import TraceStore, json_value, redact
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


def evaluate(agent, *, output, environ, timeout=2400, trace_sink=None, trace_max_bytes=262144,
             on_artifacts_ready=None, max_steps=None,
             generation_count=None, case_artifact=None, control=None,
             build_coordinator=None, job_context=None, identity=None,
             runtime_services=None, expected_case_id=None, expected_content_sha256=None,
             sdk_request_options=None, generation_indices=None, partial_generation=False,
             safe_case_replay=False):
    """
    
    Run the Kuma worker in Docker and return its host artifact directory.

    This host-side function stages the Agent repository, writes worker settings,
    starts the container, waits for it, and closes its Docker session. It has two
    modes: generation_count selects Case generation; otherwise the worker
    executes a saved Case. It returns a directory, not a Case or Judge report.

    Args:
        agent: Agent registration supplying agent_id, source path, and runtime
            configuration used to stage the evaluation container.
        output: pathlib.Path for the parent output directory. A new UUID-named
            subdirectory is created for this invocation; output must support
            resolve(), so a plain string must be converted by the caller.
        environ: Environment-variable mapping used for Docker configuration and
            artifact redaction. Must contain a nonempty KUMA_API_KEY or
            DEFUZEX_API_KEY. This function does not load a .env file itself.
        timeout: Seconds to wait for the started Agent container (default 2400).
            This is not an overall deadline: preparation and cleanup have
            separate runtime limits.
        trace_sink: Optional object with emit(TraceEvent). Receives redacted,
            bounded event previews after full events are written to the local
            network trace. None disables this forwarding, not local tracing.
        trace_max_bytes: Interceptor memory-spooling threshold (default 262144).
            Larger responses spill to disk; this never truncates trace content.
        sdk_request_options: Explicit public SDK HTTP/retry/wait options. Omitted
            values retain the pinned SDK defaults, separately from timeout.
        on_artifacts_ready: Optional callback(directory: Path), invoked after
            initial request/status files exist and before container preparation.
            Used to advertise the live artifact location to the caller.
        max_steps: Optional SDK dialogue-step limit, forwarded in worker
            settings. None leaves the choice to the SDK; it is not a Case count.
        generation_count: Positive integer selecting generation mode and the
            number of Cases to prepare. The worker creates/saves Cases without
            invoking the Agent. None selects execution mode. The generation
            worker validates the count; callers should omit case_artifact here.
        generation_indices: Optional original zero-based slots to generate from
            the full generation_count selection. Other slots are not requested.
        partial_generation: Record individual generation failures and continue
            independent slots. Shared authentication/quota blocks stop the batch.
        safe_case_replay: Explicit Agent promise that whole-Case replay has no
            unsafe external side effects. Does not override SDK retry policy.
        case_artifact: Host path to a previously saved SDK Case artifact for
            execution mode. Copied into the staged repository's .kuma directory
            and passed to the worker as a repository-relative path. The worker
            requires a saved Case in execution mode rather than generating one.
        control: Optional shared RunControl for cooperative cancellation.
            None creates a fresh control for this invocation.
        build_coordinator: Optional shared Docker build coordinator, forwarded
            when constructing DockerRuntime directly. When runtime_services is
            supplied, runtime creation and shared resources are owned by it.
        job_context: Optional mapping of inherited Suite/job identity fields,
            such as suite_id, job_id, and case_index, for events and artifacts.
        identity: Optional task-specific identity mapping overriding job_context.
            This function sets agent_id, artifact_run_id, and phase itself;
            generation mode also clears case_index and case_id.
        runtime_services: Optional Suite-owned runtime services. Supplies runtime
            limits and creates the Docker runtime with shared resources. None
            uses default RuntimeLimits and constructs DockerRuntime directly.
        expected_case_id: Expected SDK Case ID for execution mode, forwarded to
            the worker to check that the loaded Case is the selected Case.
        expected_content_sha256: Expected digest of normalized Case content for
            execution mode. Forwarded to the worker alongside expected_case_id;
            this is a content digest, not the saved artifact file's byte digest.

    Returns:
        pathlib.Path: Absolute directory for this invocation, containing
        run.json, request/evaluation.json, and available evaluation artifacts
        and diagnostics. A nonzero container exit is recorded as failed but
        can still return this path. The caller must validate status and artifacts;
        returning a directory does not mean the Agent passed its Judge evaluation.

    Raises:
        ValueError: No supported SDK API key is supplied. Lower layers may also
            reject invalid configuration.
        RunCancelled: Cooperative cancellation is observed.
        Other preparation, Docker, timeout, trace-validation, callback, I/O, or
        cleanup exceptions propagate. Once the orchestration try block begins,
        failure status is recorded and session cleanup is attempted; this does
        not guarantee artifacts exist if initial setup or disk writes fail.

    Notes:
        Successful execution-mode container exits undergo host trace validation
        before returning. Generation mode skips that Agent trace requirement.
        A trace rejection raises even when the worker already saved a report.
    """
    control = control or RunControl()
    control.check()
    limits = runtime_services.limits if runtime_services is not None else RuntimeLimits()
    preparation = Deadline.after(limits.preparation_seconds)
    if not (environ.get('KUMA_API_KEY') or environ.get('DEFUZEX_API_KEY')):
        raise ValueError('KUMA_API_KEY or DEFUZEX_API_KEY is required')

    # Create the artifact directory for this task.
    directory = output.resolve() / uuid4().hex
    directory.mkdir(parents=True, mode=0o700)
    files = Artifacts(directory, environ=environ)
    inputs = directory / 'request'; inputs.mkdir()
    # The Case artifact is addressed inside the Run repository; the host copies the
    # prepared file into the repository ledger below, before the container starts.
    reused = f'.kuma/{Path(case_artifact).name}' if case_artifact is not None else None
    files.save('request/evaluation.json', {
        'sdk_request_options': sdk_request_options or {},
        'max_steps': max_steps,
        'mode': 'generate' if generation_count is not None else 'execute',
        'count': generation_count, 'case_artifact': reused,
        'case_indices': generation_indices, 'allow_partial': partial_generation,
        'expected_case': {'case_id': expected_case_id, 'content_sha256': expected_content_sha256}})
    destination = directory / 'evaluation'; destination.mkdir(mode=0o777); destination.chmod(0o777)
    identity = {**dict(job_context or {}), **dict(identity or {}),
                'agent_id': agent.agent_id, 'artifact_run_id': directory.name,
                'phase': 'generate' if generation_count is not None else 'execute'}
    identity.setdefault('case_index', None)
    identity.setdefault('case_id', None)
    identity.setdefault('sdk_run_id', None)
    if generation_count is not None:
        identity.update(case_index=None, case_id=None)
    status = {**identity, 'schema': 'abb.evaluate.run.v1', 'run_id': directory.name,
              'status': 'running', 'cleanup_status': 'pending', 'host_trace_validation': 'not_performed',
              'safe_case_replay': safe_case_replay is True}
    files.save('run.json', status)
    session = None
    primary_error = None
    try:
        if on_artifacts_ready is not None:
            on_artifacts_ready(directory)
        control.check()

        # The container worker calls create_run/save_case for Case preparation.
        with evaluation_agent(agent, control=control, deadline=preparation) as descriptor:
            # SDK requires repo and its ledger on the same filesystem. Mount the
            # actual staged Agent source read-only, with only its .kuma writable.
            repository = directory / 'sdk-repo'
            def checked_copy(source, target):
                control.check()
                preparation.check()
                with open(source, 'rb') as incoming, open(target, 'wb') as outgoing:
                    while chunk := incoming.read(1024 * 1024):
                        control.check()
                        preparation.check()
                        outgoing.write(chunk)
                shutil.copystat(source, target)
                return target
            shutil.copytree(descriptor.path / 'agent', repository, ignore=_ignore,
                            copy_function=checked_copy)
            state = repository / '.kuma'; state.mkdir(mode=0o777); state.chmod(0o777)
            if case_artifact is not None:
                shutil.copyfile(case_artifact, state / Path(case_artifact).name)
            store = TraceStore(directory / 'network.jsonl', directory.name,
                               source='interceptor', context=identity, environ=environ)
            class Sink:
                def emit(self, event):
                    # Preserve full evidence before handing a bounded summary to UI.
                    store.emit(event)
                    if trace_sink is not None:
                        data = _trace_preview(redact(json_value(event.data), files.secrets))
                        data.update(redact({**identity, 'artifact_directory': str(directory)}, files.secrets))
                        trace_sink.emit(TraceEvent(event.event, data))
            runtime_options = dict(
                environ=environ, policy=EvaluationPolicy(state), trace_sink=Sink(),
                trace_max_bytes=trace_max_bytes, control=control, identity=identity,
                run_id=directory.name, artifact_root=directory,
            )
            if runtime_services is not None:
                runtime = runtime_services.create_docker_runtime(**runtime_options)
            else:
                runtime = DockerRuntime(build_coordinator=build_coordinator, **runtime_options)
            control.check()

            # Start the container process, then wait for its generation/execution mode.
            session = runtime.start(descriptor, 
                                    invocation=(inputs, destination),
                                    preparation_deadline=preparation)
            checkpoint = session.trace_checkpoint()
            code = session.wait(timeout=timeout)
            status['exit_code'] = code
            # Preparation calls the SDK only; no Agent/LLM invocation exists.
            if generation_count is None:
                from .diagnostics import read_diagnostic
                summary = read_diagnostic(directory, 'evaluation/manifest.json')
                judge_only_failure = (
                    summary.get('phase') == 'judge' and summary.get('execution') == 'succeeded'
                    and summary.get('otel') == 'complete' and summary.get('submission') == 'committed'
                    and summary.get('evidence') == 'captured')
                if code == 0 or judge_only_failure:
                    status['host_trace_validation'] = 'failed'
                    session.validate_trace(checkpoint)
                    status['host_trace_validation'] = 'succeeded'
            status['status'] = 'succeeded' if code == 0 else 'failed'
    except BaseException as exc:
        primary_error = exc
        status.update(status='cancelled' if isinstance(exc, RunCancelled) else 'failed',
                      error_type=type(exc).__name__, error=str(exc))
        if isinstance(exc, DockerCleanupError):
            status.update(cleanup_status='failed', cleanup_error_type=type(exc).__name__,
                          cleanup_error=str(exc))
        raise
    finally:
        try:
            if session is not None:
                try:
                    session.close()
                    status['cleanup_status'] = 'succeeded'
                except BaseException as exc:
                    status.update(status='failed', cleanup_status='failed',
                                  cleanup_error_type=type(exc).__name__, cleanup_error=str(exc))
                    raise
                finally:
                    files.save('diagnostics.json', {
                        'stdout': session.stdout, 'stderr': session.stderr,
                        'cleanup_status': status['cleanup_status'],
                        'cleanup_error': status.get('cleanup_error'), **identity,
                    })
            else:
                if status['cleanup_status'] != 'failed':
                    status['cleanup_status'] = 'not_started'
        finally:
            from .diagnostics import collect_artifacts
            status['artifacts'] = collect_artifacts(directory, status, environ=environ)
            if primary_error is not None:
                primary_error.artifacts = status['artifacts']
            manifest = destination / 'manifest.json'
            if manifest.is_file() and not manifest.is_symlink():
                try:
                    status['sdk_run_id'] = json.loads(manifest.read_text()).get('run_id')
                except (OSError, ValueError, AttributeError):
                    pass  # Preserve the original container/validation outcome.
            files.save('run.json', status)
    return directory


def _trace_preview(value, *, depth=0, budget=None):
    """Bound queued UI values while keeping common payload preview shapes."""
    budget = [4096] if budget is None else budget
    if budget[0] <= 0:
        return None
    if isinstance(value, str):
        limit = min(512, budget[0])
        result = value[:limit] + ('…' if len(value) > limit else '')
        budget[0] -= len(result)
        return result
    if depth >= 5:
        return _trace_preview(str(value), budget=budget)
    if isinstance(value, Mapping):
        result = {}
        for key, item in list(value.items())[:24]:
            if budget[0] <= 0:
                break
            key = str(key)[:64]
            budget[0] -= len(key) + 8
            result[key] = _trace_preview(item, depth=depth + 1, budget=budget)
        return result
    if isinstance(value, list):
        return [_trace_preview(item, depth=depth + 1, budget=budget)
                for item in value[-4:] if budget[0] > 0]
    budget[0] -= 24
    return value
