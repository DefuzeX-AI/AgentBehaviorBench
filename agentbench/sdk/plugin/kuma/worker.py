"""Official KUMA and the existing Agent worker, in one container process."""
import argparse
import asyncio
import json
import os
import platform
from pathlib import Path
from uuid import uuid4
from importlib.metadata import version
from agentbench.sdk.common.artifacts import Artifacts
from agentbench.sdk.common.input_binding import InputBinding
from .runner import drive_run
from agentbench.runtime.agentcontainer.session import AgentSession


async def execute(root, output, settings=None):
    from kuma import create_run
    from kuma.otel import configure_trace_evidence
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.resources import Resource
    from agentbench.runtime.agentcontainer.worker import execute as invoke_agent, configure_trust
    from agentbench.runtime.agentcontainer.config import tomllib
    files = Artifacts(output)
    provider = TracerProvider(resource=Resource.create({'service.name': 'abb-evaluation'}))
    capture = configure_trace_evidence(provider)
    with (root / 'agent.toml').open('rb') as stream:
        manifest = tomllib.load(stream)
    run = None
    agent_session = AgentSession()
    settings = dict(settings or {})
    try:
        binding = InputBinding.from_file(root / 'evaluation/input-contract.json')
        configure_trust()
        files.save('process.json', {'pid': os.getpid(), 'container': platform.node(), 'mode': 'official',
                   'sdk': 'kuma', 'sdk_version': version('kuma-defuzex'), 'agent_id': manifest['agent_id'],
                   'source': manifest.get('source'), 'repo': str(root / 'agent')})
        files.save('manifest.json', {'phase': 'case_generation', 'judge': 'pending'})
        options = dict(repo_path=root / 'agent',
                       max_steps=settings.get('max_steps'), allow_local=False, track_files=False, save_local=True,
                       api_key=os.environ.get('KUMA_API_KEY') or os.environ.get('DEFUZEX_API_KEY'),
                       trace_evidence=capture, max_retries=0, operation_wait_timeout=600)
        if settings.get('mode') == 'generate':
            from .generation import generate_collection
            # Generation reads the Agent profile; reuse rejects it, so the profile
            # belongs only to this branch.
            collection = generate_collection(
                create_run, count=settings['count'], files=files, repo=root / 'agent',
                options=dict(options, agent_profile_path=root / 'evaluation/profile.md'))
            files.save('manifest.json', {'phase': 'batch_generated', 'count': len(collection['cases'])})
            return 0
        if settings.get('case_artifact') is None:
            raise ValueError('Evaluation requires a prepared Case artifact; generation belongs to batch preparation')
        # The SDK reuses a Case only from a saved artifact file inside the Run repository,
        # and rejects a Profile or strategy alongside it: the Case is already decided.
        run = create_run(case_path=settings['case_artifact'], **options)
        # Current SDK has no public Case accessor. Keep this version-sensitive
        # snapshot in the KUMA boundary; never manufacture an official Case ID.
        from kuma.serialization import to_json
        files.save('case.json', to_json(run._case))
        from agentbench.sdk.common.case_identity import case_content_sha256
        fingerprint = case_content_sha256(run._case)
        duplicate = fingerprint in settings.get('excluded_cases', [])
        files.save('case-selection.json', {'case_id': run.case_id, 'content_sha256': fingerprint,
                                          'status': 'duplicate' if duplicate else 'accepted'})
        if duplicate:
            raise ValueError('SDK returned duplicate Case content; no Agent steps were executed')
        from agentbench.observe.store import TraceStore
        TraceStore(output / 'sdk.jsonl', run.run_id, source='sdk').record(
            'case_generated', case_id=run.case_id, artifact='case.json')
        async def invoke(payload, folder, shared_provider):
            request = folder / 'request.json'
            invocation_id = uuid4().hex
            observed_input = json.loads((folder / 'input.json').read_text())
            files.save(str(request.relative_to(output)), {
                'schema': 'abb.invocation.v1', 'run_id': invocation_id, 'session_id': run.run_id,
                'observation_context': {key: observed_input[key] for key in ('case_id', 'input_id') if isinstance(observed_input.get(key), str)},
                'agent_id': manifest['agent_id'], 'framework': manifest['framework'], 'input': payload})
            await invoke_agent(root, request, folder, provider=shared_provider, session=agent_session)
            return json.loads((folder / 'result.json').read_text())
        summary = await drive_run(run, binding,
                                  invoke, output, provider=provider)
        return 0 if (summary['judge'] == 'received' and summary['otel'] == 'complete'
                     and summary['evidence'] == 'captured'
                     and summary['execution'] == 'succeeded') else 1
    except Exception as exc:
        files.save('error.json', {'phase': 'case_generation' if run is None else 'evaluation',
                   'type': type(exc).__name__, 'message': str(exc), 'code': getattr(exc, 'code', None),
                   'request_id': getattr(exc, 'request_id', None)})
        return 1
    finally:
        try:
            await agent_session.aclose()
        finally:
            files.save('session.json', agent_session.snapshot())
            if run is not None and run.state in ('ready', 'input_delivered'):
                run.cancel()
            provider.force_flush()
            provider.shutdown()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agent-root', type=Path, default=Path('/opt/agent'))
    parser.add_argument('--output', type=Path, default=Path('/run/abb-output'))
    parser.add_argument('--settings', type=Path, default=Path('/run/abb-input/evaluation.json'))
    args = parser.parse_args()
    settings = json.loads(args.settings.read_text()) if args.settings.is_file() else {}
    return asyncio.run(execute(args.agent_root, args.output, settings))


if __name__ == '__main__':
    raise SystemExit(main())
