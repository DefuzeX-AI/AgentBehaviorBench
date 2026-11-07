"""KUMA settings and diagnostics for ABB's shared container execution."""
from functools import partial
from pathlib import Path

from agentbench.runtime.docker.execution_policy import ControllerExecutionPolicy
from agentbench.sdk.contracts import SDKRunnerContext
from agentbench.sdk.integration.execution import run_evaluation
from .configuration import SDK_REPOSITORY, backend_url
from .image import evaluation_agent


class EvaluationPolicy(ControllerExecutionPolicy):
    """Compatibility for callers supplying KUMA's ledger directory."""

    def __init__(self, state, *, repository=None, target=SDK_REPOSITORY,
                 writable=False, replay=None, channel=None, publications=()):
        state = state.resolve()
        super().__init__(state.parent, repository=repository or state.parent,
                         target=target, writable=writable, replay=replay,
                         channel=channel, publications=publications)


def _completed_execution(directory):
    """A failed Judge can still leave a committed, evidence-complete execution."""
    from .diagnostics import read_diagnostic
    summary = read_diagnostic(directory, 'manifest.json')
    return (summary.get('phase') == 'judge'
            and summary.get('execution') in ('succeeded', 'failed')
            and summary.get('otel') == 'complete'
            and summary.get('submission') == 'committed'
            and summary.get('evidence') == 'captured')


def evaluate(agent, *, output, environ, timeout=2400, trace_sink=None, trace_max_bytes=262144,
             on_artifacts_ready=None, max_steps=None,
             generation_count=None, case_artifact=None, control=None,
             build_coordinator=None, job_context=None, identity=None,
             runtime_services=None, expected_case_id=None, expected_content_sha256=None,
             sdk_request_options=None, generation_indices=None, partial_generation=False,
             expected_environment_sha256=None,
             safe_case_replay=False, require_credentials=True, overlay=None, defer_judge=False,
             artifact_store=None):
    """Translate KUMA settings, then execute through the shared runtime.

    Case generation/save/reuse, Judge recovery and result interpretation remain
    owned by this plugin. The returned directory must be validated by its runner.
    """
    from .diagnostics import collect_artifacts
    if control is not None:
        control.check()
    if require_credentials and not (environ.get('KUMA_API_KEY') or environ.get('DEFUZEX_API_KEY')):
        raise ValueError('KUMA_API_KEY or DEFUZEX_API_KEY is required')
    context = SDKRunnerContext(
        environ=environ, model=None, trace_sink=trace_sink, trace_max_bytes=trace_max_bytes,
        control=control, build_coordinator=build_coordinator,
        job_context={**dict(job_context or {}), **dict(identity or {})},
        runtime_services=runtime_services, artifacts=artifact_store)
    reused = f'.kuma/{Path(case_artifact).name}' if case_artifact is not None else None
    settings = {
        'defer_judge': defer_judge, 'sdk_request_options': sdk_request_options or {},
        'max_steps': max_steps,
        'mode': 'generate' if generation_count is not None else 'execute',
        'count': generation_count, 'case_artifact': reused,
        'case_indices': generation_indices, 'allow_partial': partial_generation,
        'expected_case': {'case_id': expected_case_id, 'content_sha256': expected_content_sha256}}
    overlay_options = dict(backend=backend_url(environ)) if overlay is None else dict(overlay)
    return run_evaluation(
        agent, context=context, output=output,
        stage_agent=partial(evaluation_agent, **overlay_options), settings=settings,
        execute_agent=generation_count is None, timeout=timeout,
        on_artifacts_ready=on_artifacts_ready, private_directories=('.kuma',),
        private_files={reused: case_artifact} if reused is not None else None,
        generation_indices=(generation_indices if generation_indices is not None else
                            tuple(range(generation_count)) if generation_count is not None else None),
        expected_environment_sha256=expected_environment_sha256,
        require_workspace_identity=case_artifact is not None,
        safe_case_replay=safe_case_replay, validate_failed_execution=_completed_execution,
        collect_artifacts=collect_artifacts,
        excluded_agent_environment=('KUMA_API_KEY', 'DEFUZEX_API_KEY', 'KUMA_BASE_URL'),
        repository_target=SDK_REPOSITORY)
