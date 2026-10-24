"""Shared container execution for implementations of EvaluationRunner.

SDK formats remain opaque settings and private files. SDKRunnerContext supplies
cancellation, runtime services and ArtifactStore; this module owns the workspace,
isolated processes, evidence validation and cleanup.
"""
from collections.abc import Mapping
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile

from agentbench.observe.timing import span, timing_session
from agentbench.observe.store import TraceStore, json_value, redact
from agentbench.runtime.contracts.execution import Deadline, DockerCleanupError, RunCancelled, RunControl, RuntimeLimits
from agentbench.runtime.docker import DockerRuntime
from agentbench.runtime.docker.execution_policy import ControllerExecutionPolicy
from agentbench.runtime.docker.worker_build import _ignore
from agentbench.runtime.interception import TraceEvent
from agentbench.runtime.agentcontainer.config import tomllib
from agentbench.sdk.contracts import SDKRunnerContext
from agentbench.sdk.common.artifacts import Artifacts
from agentbench.sdk.common.output_permissions import prepare_output
from agentbench.sdk.common.workspace import workspace_policy, prepare_workspace, workspace_digest


def _private_path(root, relative):
    """Resolve a plugin-owned file beneath controller-only storage."""
    path = PurePosixPath(relative)
    if (not path.parts or path.is_absolute() or path.as_posix() != relative
            or any(part in ('..', '.') for part in path.parts) or ':' in relative
            or '\\' in relative):
        raise ValueError('SDK private paths must be canonical relative paths')
    target = root.joinpath(*path.parts)
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError('SDK private path escapes controller storage')
    return target


def run_evaluation(agent, *, context: SDKRunnerContext, output, stage_agent,
                   settings=None, execute_agent=True, timeout=2400,
                   on_artifacts_ready=None, private_directories=(), private_files=None,
                   generation_indices=None, expected_environment_sha256=None,
                   require_workspace_identity=False,
                   safe_case_replay=False, validate_failed_execution=None,
                   collect_artifacts=None, excluded_agent_environment=(),
                   repository_target='/opt/abb-sdk-repo'):
    """Run an SDK worker using the host facilities supplied to its runner.

    ``stage_agent`` is an image-staging context manager, usually a partial of
    runtime.docker.evaluation_image.evaluation_image. ``settings`` is the SDK's
    own request; shared execution paths and limits are added before startup.
    ``private_files`` maps relative storage paths to host files; none are mounted
    in the Agent. ``generation_indices`` allocates Case slots before generation.
    Saved Cases can require a matching workspace identity; arbitrary private SDK
    configuration files do not imply Case replay.

    Returns the artifact directory. The caller interprets its SDK's report and
    exit status; a returned directory alone is not a successful evaluation.
    Failed executions may explicitly request host trace validation, for example
    when a remote Judge failed after the Agent finished. Artifact enrichment is
    also SDK-owned. Neither callback runs an Agent or changes Case identity.
    """
    environ = dict(context.environ)
    if context.model is not None:
        environ['ABB_MODEL'] = context.model
    control = context.control or RunControl()
    runtime_services = context.runtime_services
    build_coordinator = context.build_coordinator
    artifact_store = context.artifacts
    trace_sink = context.trace_sink
    trace_max_bytes = context.trace_max_bytes
    identity = dict(context.job_context or {})
    settings = dict(settings or {})
    control.check()
    limits = runtime_services.limits if runtime_services is not None else RuntimeLimits()
    preparation = Deadline.after(limits.preparation_seconds)

    # Create the artifact directory for this task.
    from agentbench.sdk.integration.lifecycle import allocate_run
    directory = allocate_run(output, artifact_store, agent.agent_id, identity,
                             (generation_indices or ()) if not execute_agent else None)
    Path(directory).mkdir(parents=True, mode=0o700, exist_ok=True)
    from agentbench.sdk.integration.context import ResponseLimits
    response_limits = ResponseLimits.from_environ(environ)
    files = Artifacts(directory, environ=environ)
    (directory / 'logs').mkdir(exist_ok=True)
    with timing_session(directory / 'logs/host-timing.jsonl', source='host', name='Evaluation',
                        identity={**identity, 'agent_id': agent.agent_id}) as timing_root:
        inputs = directory / 'request'; Path(inputs).mkdir()
        files.save('request/evaluation.json', settings)
        destination = prepare_output(directory)
        identity = {**identity,
                    'agent_id': agent.agent_id, 'artifact_run_id': directory.name,
                    'phase': 'execute' if execute_agent else 'generate'}
        identity.setdefault('case_index', None)
        identity.setdefault('case_id', None)
        identity.setdefault('sdk_run_id', None)
        if not execute_agent:
            identity.update(case_index=None, case_id=None)
        status = {**identity, 'schema': 'abb.evaluate.run.v1', 'run_id': directory.name,
                  'status': 'running', 'cleanup_status': 'pending', 'host_trace_validation': 'not_performed',
                  'safe_case_replay': safe_case_replay is True}
        files.save('run.json', status)
        session = None
        agent_process = None
        agent_checkpoint = None
        workspace_temp = None
        primary_error = None
        try:
            if on_artifacts_ready is not None:
                on_artifacts_ready(directory)
            control.check()

            with stage_agent(agent, control=control, deadline=preparation) as descriptor:
                # Keep the tracked source/workspace separate from private SDK storage.
                # Only the trusted controller mounts the ledger.
                repository = directory / 'sdk-source'
                def checked_copy(source, target):
                    control.check()
                    preparation.check()
                    with Path(source).open('rb') as incoming, Path(target).open('wb') as outgoing:
                        while chunk := incoming.read(1024 * 1024):
                            control.check()
                            preparation.check()
                            outgoing.write(chunk)
                    shutil.copystat(Path(source), Path(target))
                    return target
                with span('Prepare Case workspace', kind='preparation'):
                    policy = workspace_policy(tomllib.loads((descriptor.path / 'agent.toml').read_text()))
                    target = policy.path or repository_target
                    ledger_root = directory / 'sdk-repo'
                    Path(ledger_root).mkdir()
                    if policy.path:
                        workspace_temp = tempfile.TemporaryDirectory(prefix='.abb-workspace-', dir=Path(directory.parent))
                        repository = Path(workspace_temp.name)
                        contract = prepare_workspace(descriptor.path, repository, policy)
                        Path(repository).chmod(0o777)
                        for item in Path(repository).rglob('*'):
                            item.chmod(0o777 if item.is_dir() else (item.stat().st_mode & 0o111) | 0o666)
                        files.save('workspace.json', contract)
                        settings_path = directory / 'request/evaluation.json'
                        settings = json.loads(Path(settings_path).read_text())
                        settings['workspace'] = contract
                        files.save('request/evaluation.json', settings)
                        if require_workspace_identity or expected_environment_sha256 is not None:
                            if expected_environment_sha256 is None:
                                raise ValueError('Saved Case has no workspace contract; generate new Cases for this workspace')
                            if expected_environment_sha256 != workspace_digest(contract):
                                raise ValueError('Saved Case workspace differs; no Agent steps were executed')
                    else:
                        shutil.copytree(Path(descriptor.path / 'agent'), Path(repository), ignore=_ignore,
                                        copy_function=checked_copy)
                    for relative in private_directories:
                        path = _private_path(ledger_root, relative)
                        Path(path).mkdir(parents=True, mode=0o700, exist_ok=True)
                        Path(path).chmod(0o700)
                    for relative, source in (private_files or {}).items():
                        path = _private_path(ledger_root, relative)
                        Path(path.parent).mkdir(parents=True, mode=0o700, exist_ok=True)
                        checked_copy(source, path)
                store = TraceStore(directory / 'logs/network.jsonl', directory.name,
                                   source='interceptor', context=identity, environ=environ)
                class Sink:
                    def emit(self, event):
                        # Preserve full evidence before handing a bounded summary to UI.
                        store.emit(event)
                        if trace_sink is not None:
                            data = _trace_preview(redact(json_value(event.data), files.secrets))
                            data.update(redact({**identity, 'artifact_directory': str(directory)}, files.secrets))
                            trace_sink.emit(TraceEvent(event.event, data))
                replay_directory = None
                if execute_agent:
                    replay_directory = directory / 'replay'
                    Path(replay_directory).mkdir(mode=0o777)
                    Path(replay_directory).chmod(0o777)
                from agentbench.sdk.integration.context import ExecutionChannel
                channel = ExecutionChannel.create(directory / 'channel') if execute_agent else None
                settings = json.loads(Path(directory / 'request/evaluation.json').read_text())
                publications = ()
                if artifact_store is not None and not execute_agent:
                    indices = generation_indices or ()
                    publications = tuple((index, artifact_store.case(agent.agent_id, index).directory)
                                         for index in indices)
                    settings['case_publications'] = {str(index): f'/run/abb-published/{index}'
                                                     for index, _ in publications}
                settings.update(private_storage='/run/abb-sdk-storage',
                                isolated_agent=channel is not None, agent_timeout=timeout)
                settings['agent_response_limits'] = {
                    'max_bytes': response_limits.max_bytes, 'max_files': response_limits.max_files}
                files.save('request/evaluation.json', settings)
                runtime_options = dict(
                    environ=environ, policy=ControllerExecutionPolicy(ledger_root, repository=repository, target=target, writable=bool(policy.path), replay=replay_directory, channel=channel, publications=publications), trace_sink=Sink(),
                    trace_max_bytes=trace_max_bytes, control=control, identity=identity,
                    timeout_sec=timeout,
                    run_id=directory.name, artifact_root=directory,
                )
                if runtime_services is not None:
                    runtime = runtime_services.create_docker_runtime(**runtime_options)
                else:
                    runtime = DockerRuntime(build_coordinator=build_coordinator, **runtime_options)
                control.check()
                if channel is not None:
                    from agentbench.runtime.docker.execution_policy import AgentExecutionPolicy
                    public_inputs = directory / 'agent-request'
                    Path(public_inputs).mkdir()
                    agent_outputs = directory / 'agent-output'
                    Path(agent_outputs).mkdir(mode=0o700)
                    options = dict(runtime_options)
                    options['policy'] = AgentExecutionPolicy(repository, target, bool(policy.path), channel, agent_outputs)
                    options['artifact_root'] = directory / 'agent-runtime'
                    Path(options['artifact_root']).mkdir()
                    options['run_id'] = directory.name + '-agent'
                    agent_runtime = (runtime_services.create_docker_runtime(**options)
                                     if runtime_services is not None else
                                     DockerRuntime(build_coordinator=build_coordinator, **options))
                    agent_process = agent_runtime.start(
                        descriptor, invocation=(public_inputs, agent_outputs),
                        argv=('python', '-m', 'agentbench.runtime.agentcontainer.channel'),
                        exclude_environment=tuple(tomllib.loads((descriptor.path / 'agent.toml').read_text())
                                                  .get('runtime', {}).get('worker_env_keys', ())) +
                                            tuple(excluded_agent_environment),
                        preparation_deadline=preparation)
                    agent_checkpoint = agent_process.trace_checkpoint()

                # Start the container process, then wait for its generation/execution mode.
                session = runtime.start(descriptor,
                                        invocation=(inputs, destination),
                                        preparation_deadline=preparation)
                checkpoint = session.trace_checkpoint()
                with span('Container execution', kind='container') as container_timing:
                    code = session.wait(timeout=timeout)
                    container_timing.status = 'succeeded' if code == 0 else 'failed'
                status['exit_code'] = code
                # Preparation calls the SDK only; no Agent/LLM invocation exists.
                if execute_agent:
                    should_validate = code == 0 or (
                        validate_failed_execution is not None and validate_failed_execution(directory))
                    if should_validate:
                        status['host_trace_validation'] = 'failed'
                        with span('Validate network evidence', kind='evidence'):
                            session.validate_trace(checkpoint)
                            if agent_process is not None:
                                agent_process.validate_trace(agent_checkpoint)
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
                errors = []
                for active, label in ((session, 'controller'), (agent_process, 'agent')):
                    if active is None:
                        continue
                    try:
                        with span('Cleanup ' + label + ' container', kind='cleanup'):
                            active.close()
                    except BaseException as exc:
                        errors.append(exc)
                    finally:
                        files.save('diagnostics.json' if label == 'controller' else 'agent-diagnostics.json',
                                   {'stdout': active.stdout, 'stderr': active.stderr, **identity})
                if errors:
                    exc = errors[0]
                    status.update(status='failed', cleanup_status='failed',
                                  cleanup_error_type=type(exc).__name__, cleanup_error=str(exc))
                    raise exc
                if status['cleanup_status'] != 'failed':
                    status['cleanup_status'] = 'succeeded' if session or agent_process else 'not_started'
            finally:
                status['artifacts'] = (collect_artifacts(directory, status, environ=environ)
                                       if collect_artifacts is not None else {'directory': str(directory)})
                if primary_error is not None:
                    primary_error.artifacts = status['artifacts']
                manifest = destination / 'manifest.json'
                if Path(manifest).is_file() and not Path(manifest).is_symlink():
                    try:
                        status['sdk_run_id'] = json.loads(Path(manifest).read_text()).get('run_id')
                    except (OSError, ValueError, AttributeError):
                        pass  # Preserve the original container/validation outcome.
                files.save('run.json', status)
                if (status['cleanup_status'] == 'succeeded'
                        and status['host_trace_validation'] == 'succeeded'):
                    cleanup_transport(directory)
                if workspace_temp is not None:
                    workspace_temp.cleanup()
        timing_root.status = status['status']
        return directory


def cleanup_transport(directory):
    """Retire only temporary communication after both containers are stopped."""
    root = Path(directory).resolve()
    for name in ('channel', 'agent-request', 'agent-output'):
        path = root / name
        if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()) or not path.resolve().is_relative_to(root):
            raise ValueError('Transport path leaves execution root')
        if path.is_dir():
            target = str(path)
            if os.name == 'nt' and not target.startswith('\\\\?\\'):
                target = ('\\\\?\\UNC\\' + target[2:] if target.startswith('\\\\')
                          else '\\\\?\\' + target)
            shutil.rmtree(target)


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
