"""Official KUMA and the existing Agent worker, in one container process."""
import argparse
import asyncio
import json
import os
import platform
from pathlib import Path
from uuid import uuid4
from importlib.metadata import version
from agentbench.evaluation.artifacts import Artifacts
from agentbench.evaluation.input_binding import InputBinding
from agentbench.evaluation.runner import drive_run


async def execute(root, output):
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
    try:
        configure_trust()
        files.save('process.json', {'pid': os.getpid(), 'container': platform.node(), 'mode': 'official',
                   'sdk_version': version('kuma-defuzex'), 'agent_id': manifest['agent_id'],
                   'source': manifest.get('source'), 'repo': str(root / 'agent')})
        files.save('manifest.json', {'phase': 'case_generation', 'judge': 'pending'})
        run = create_run(repo_path=root / 'agent', agent_profile_path=root / 'evaluation/profile.md',
                         max_steps=1, allow_local=False, track_files=False, save_local=True,
                         api_key=os.environ.get('KUMA_API_KEY') or os.environ.get('DEFUZEX_API_KEY'),
                         trace_evidence=capture, max_retries=0, operation_wait_timeout=600)
        # Current SDK has no public Case accessor. Keep this version-sensitive
        # snapshot in the KUMA boundary; never manufacture an official Case ID.
        from kuma.serialization import to_json
        files.save('case.json', to_json(run._case))
        async def invoke(payload, folder, shared_provider):
            request = folder / 'request.json'
            invocation_id = uuid4().hex
            files.save(str(request.relative_to(output)), {
                'schema': 'abb.invocation.v1', 'run_id': invocation_id, 'session_id': run.run_id,
                'agent_id': manifest['agent_id'], 'framework': manifest['framework'], 'input': payload})
            await invoke_agent(root, request, folder, provider=shared_provider)
            return json.loads((folder / 'result.json').read_text())
        summary = await drive_run(run, InputBinding.from_file(root / 'evaluation/input-contract.json'),
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
        if run is not None and run.state in ('ready', 'input_delivered'):
            run.cancel()
        provider.force_flush()
        provider.shutdown()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agent-root', type=Path, default=Path('/opt/agent'))
    parser.add_argument('--output', type=Path, default=Path('/run/abb-output'))
    args = parser.parse_args()
    return asyncio.run(execute(args.agent_root, args.output))


if __name__ == '__main__':
    raise SystemExit(main())
