"""Official KUMA and the existing Agent worker, in one container process."""
import argparse
import asyncio
import json
import os
import platform
import sys
import traceback
from pathlib import Path
from uuid import uuid4
from importlib.metadata import version
from agentbench.sdk.common.artifacts import Artifacts
from .runner import drive_run
from .configuration import SDK_REPOSITORY, request_options, api_key
from .compatibility import run_case
from agentbench.runtime.agentcontainer.session import AgentSession


async def execute(root, output, settings=None, sdk_repo=None):
    # sdk_repo is the SDK repository/ledger root, mounted apart from the Agent tree
    # so the image's own /opt/agent/agent stays visible; in place when omitted.
    repository = Path(sdk_repo) if sdk_repo is not None else root / 'agent'
    # Enter the in-container evaluation flow. root is the Agent directory,
    # output stores artifacts, and settings contains the job configuration.
    # Import the official KUMA SDK, evidence capture, and Agent invocation here.
    from kuma import create_run, DEFAULT_BASE_URL
    from kuma.otel import configure_trace_evidence
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.resources import Resource
    from agentbench.runtime.agentcontainer.worker import execute as invoke_agent, configure_trust
    from agentbench.runtime.agentcontainer.config import tomllib



    
    # Prepare artifact storage and connect OpenTelemetry evidence to the KUMA SDK.
    files = Artifacts(output)
    provider = TracerProvider(resource=Resource.create({'service.name': 'abb-evaluation'}))
    capture = configure_trace_evidence(provider)
    
    # Read the in-container Agent manifest for its ID and framework.
    with (root / 'agent.toml').open('rb') as stream:
        manifest = tomllib.load(stream)
    # Create the reusable Agent session before the SDK Run exists.
    run = None
    agent_session = AgentSession()
    settings = dict(settings or {})
    try:
        # Pass each current input directly to the adapter. The Agent owns history
        # and memory, so no per-Agent input contract is required.
        configure_trust()
        # Save process, SDK, and initial state metadata for progress inspection.
        credential, credential_source = api_key(os.environ)
        files.save('process.json', {'pid': os.getpid(), 'container': platform.node(), 'mode': 'official',
                   'sdk': 'kuma', 'sdk_version': version('kuma-defuzex'), 'agent_id': manifest['agent_id'],
                   'sdk_base_url': DEFAULT_BASE_URL,
                   'api_key_source': credential_source,
                   'source': manifest.get('source'), 'repo': str(repository)})
        files.save('manifest.json', {'phase': 'case_generation', 'judge': 'pending'})

        # Assemble SDK options for the repository, step limit, credentials,
        # trace evidence, and request timing.
        options = dict(repo_path=repository,
                       max_steps=settings.get('max_steps'), 
                       allow_local=False, track_files=False, 
                       save_local=True,

                       api_key=credential, trace_evidence=capture,
                       **request_options(settings.get('sdk_request_options')))

        
        if settings.get('mode') == 'generate':
            # Generation mode creates and saves Cases from the Agent Profile
            # without invoking the Agent.
            from .generation import generate_collection
            # The registered requirement.md is the SDK Agent Profile. Reusing a
            # saved Case rejects a profile, so supply it only during generation.
            collection = generate_collection(
                create_run, count=settings['count'], files=files, repo=repository,
                case_indices=settings.get('case_indices'), allow_partial=settings.get('allow_partial', False),
                options=dict(options, agent_profile_path=root / 'requirement.md'))
            complete = not collection['failures'] and not collection['unattempted_indices']
            files.save('manifest.json', {'phase': 'batch_generated' if complete else 'batch_partial',
                                        'count': len(collection['cases']),
                                        'failed_count': len(collection['failures']),
                                        'unattempted_indices': collection['unattempted_indices']})
            # Stop after batch generation instead of entering Case execution.
            return 0 if complete else 1
        
        # Execution mode requires a previously saved Case artifact.
        if settings.get('case_artifact') is None:
            raise ValueError('Evaluation requires a prepared Case artifact; generation belongs to batch preparation')
        # The SDK reuses a Case only from a saved artifact file inside the Run repository,
        # and rejects a Profile or strategy alongside it: the Case is already decided.
        # Create the SDK Run from the saved Case without generating another one.
        run = create_run(case_path=settings['case_artifact'], **options)


        # Current SDK has no public Case accessor. Keep this version-sensitive
        # snapshot in the KUMA boundary; never manufacture an official Case ID.
        # Save the Case actually loaded by the SDK for host-side validation.
        case = run_case(run)
        files.save('case.json', case)
        from agentbench.sdk.common.case_identity import case_content_sha256
        # Match the Case ID and content digest supplied by the host.
        fingerprint = case_content_sha256(case)
        expected = settings['expected_case']
        matched = run.case_id == expected['case_id'] and fingerprint == expected['content_sha256']
        files.save('case-selection.json', {'case_id': run.case_id, 'content_sha256': fingerprint,
                                          'expected_case': expected,
                                          'status': 'accepted' if matched else 'rejected'})
        if not matched:
            raise ValueError('SDK Case does not match the prepared identity; no Agent steps were executed')
        # Retain the case_generated event name even though this loads a saved Case.
        from agentbench.observe.store import TraceStore
        TraceStore(output / 'sdk.jsonl', run.run_id, source='sdk').record(
            'case_generated', case_id=run.case_id, artifact='case.json')

        
        async def invoke(payload, folder, shared_provider):
            # Reuse one Agent session for every turn and pass only the current input.
            # shared_provider is the common trace provider for the Case.
            request = folder / 'request.json'
            invocation_id = uuid4().hex
            observed_input = json.loads((folder / 'input.json').read_text())
            # Persist the invocation request with Case, input, and session identity.
            files.save(str(request.relative_to(output)), {
                'schema': 'abb.invocation.v1', 'run_id': invocation_id, 'session_id': run.run_id,
                'observation_context': {key: observed_input[key] for key in ('case_id', 'input_id') if isinstance(observed_input.get(key), str)},
                'agent_id': manifest['agent_id'], 'framework': manifest['framework'], 'input': payload})
            # Invoke the Agent and wait for this turn to complete.
            await invoke_agent(root, request, folder, provider=shared_provider, session=agent_session)
            # Return the Agent result to the SDK dialogue driver.
            return json.loads((folder / 'result.json').read_text())
        # Drive the Case by receiving inputs, invoking the Agent, submitting
        # outputs, and collecting the Judge report.
        summary = await drive_run(run, invoke, output, provider=provider, repo_path=repository)
        # The worker exit code checks execution and evidence completeness,
        # independently of whether the Judge verdict is pass.
        return 0 if (summary['judge'] == 'received' and summary['otel'] == 'complete'
                     and summary['evidence'] == 'captured'
                     and summary['execution'] == 'succeeded') else 1
    except Exception as exc:
        # Persist error details and return exit code 1 to the host.
        files.save('error.json', {'phase': 'case_generation' if run is None else 'evaluation',
                   'type': type(exc).__name__, 'message': str(exc), 'code': getattr(exc, 'code', None),
                   'retryable': getattr(exc, 'retryable', None), 'client_request_id': getattr(exc, 'client_request_id', None),
                   'request_id': getattr(exc, 'request_id', None)})
        return 1
    finally:
        # Always close the Agent session and save its final state.
        try:
            await agent_session.aclose()
        finally:
            files.save('session.json', agent_session.snapshot())
            # Cancel an unfinished SDK Run that is still waiting for input or submission.
            if run is not None and run.state in ('ready', 'input_delivered'):
                run.cancel()
            # Flush traces and close the provider last.
            provider.force_flush()
            provider.shutdown()


class EvaluationSettingsError(RuntimeError):
    """The host-mounted evaluation settings could not be loaded."""


def read_settings(path):
    """Load the mandatory host settings, naming why they cannot be read.

    The host always writes this file before starting the container. A missing or
    unreadable file must stop the worker: treating it as empty settings runs the
    wrong mode and reports an unrelated error two layers later.
    """
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError as exc:
        raise EvaluationSettingsError(f'Evaluation settings are missing at {path}') from exc
    except PermissionError as exc:
        raise EvaluationSettingsError(
            f'Cannot read evaluation settings at {path}: permission denied for container '
            f'uid {os.getuid()} gid {os.getgid()}{_ownership(path)}') from exc
    except (OSError, ValueError) as exc:
        raise EvaluationSettingsError(f'Cannot read evaluation settings at {path}: {exc}') from exc
    if not isinstance(value, dict):
        raise EvaluationSettingsError(f'Evaluation settings at {path} must be a JSON object')
    return value


def _ownership(path):
    try:
        info = os.stat(path)
    except OSError:
        return ''
    return f' (file owner uid {info.st_uid} gid {info.st_gid}, mode {info.st_mode & 0o777:04o})'


def main():
    # Parse Agent, artifact, and job-settings paths at the container entrypoint.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agent-root', type=Path, default=Path('/opt/agent'))
    parser.add_argument('--output', type=Path, default=Path('/run/abb-output'))
    parser.add_argument('--settings', type=Path, default=Path('/run/abb-input/evaluation.json'))
    parser.add_argument('--sdk-repo', type=Path, default=Path(SDK_REPOSITORY))
    args = parser.parse_args()
    # Read generation or execution settings from the host-mounted evaluation.json.
    try:
        settings = read_settings(args.settings)
    except EvaluationSettingsError as exc:
        # The host reads error.json; stderr alone only reaches diagnostics.json.
        Artifacts(args.output).save('error.json', {
            'phase': 'startup', 'type': type(exc).__name__, 'message': str(exc)})
        print(exc, file=sys.stderr, flush=True)
        return 1
    # Run the asynchronous flow and propagate its exit code.
    try:
        return asyncio.run(execute(args.agent_root, args.output, settings, sdk_repo=args.sdk_repo))
    except ImportError as exc:
        # The SDK and trace tooling are imported before execute() can record an
        # error. A missing module here usually means the image's `python` is not
        # the interpreter the evaluation overlay installed into, so name it.
        traceback.print_exc()
        message = f'{exc} (interpreter {sys.executable})'
        Artifacts(args.output).save('error.json', {
            'phase': 'startup', 'type': type(exc).__name__, 'message': message})
        print(message, file=sys.stderr, flush=True)
        return 1


if __name__ == '__main__':
    # Docker enters here through python -m agentbench.sdk.plugin.kuma.worker.
    raise SystemExit(main())
