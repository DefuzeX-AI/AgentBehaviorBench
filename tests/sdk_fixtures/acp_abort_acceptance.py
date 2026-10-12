"""Real ACP subprocess + installed KUMA, with an explicit offline Judge."""
import asyncio
import json
import sys
from importlib.metadata import version
from pathlib import Path
from uuid import uuid4
from kuma import create_run
from kuma.otel import configure_trace_evidence
from opentelemetry.sdk.trace import TracerProvider
from agentbench.runtime.agentcontainer.session import AgentSession
from agentbench.runtime.agentcontainer.worker import execute
from agentbench.sdk.plugin.kuma.runner import drive_run
from agentbench.sdk.plugin.kuma.compatibility import run_case
from agentbench.sdk.plugin.kuma.completion import validate_input_prefix
from agentbench.sdk.common.artifacts import Artifacts


async def main(output):
    repo = Path('/tmp/acp-abort-acceptance')
    repo.mkdir()
    server = Path(__file__).resolve().parents[1] / 'acp_fixtures/server.py'
    (repo / 'agent.toml').write_text(
        'agent_id="abort-fixture"\nframework="acp"\n[runtime]\ntimeout_sec=10\n'
        '[adapter]\ntype="acp"\ncwd="' + str(repo) + '"\ncommand=' + json.dumps([sys.executable, str(server)]) + '\n')
    profile = repo / 'requirement.md'
    profile.write_text('---\nagent_description: Echo each message, abort on the literal abort.\ninput_type: text\n---\n'
        '## Production Use Scenario\nOffline protocol testing.\n'
        '## Behaviors to Test\nPreserve partial output and stop after abort.\n'
        '## Known Limitations or Prohibited Behaviors\nNo external services.\n')
    provider = TracerProvider()
    capture = configure_trace_evidence(provider)
    def judge(context):
        assert [h.submission.status for h in context.history] == ['completed', 'aborted']
        return {'status': 'insufficient_evidence', 'issues': [],
                'summary': 'Offline custom Judge: native abort, third input unexecuted.'}
    run = create_run(repo_path=repo, agent_profile_path=profile, on_failure='stop',
        case_provider=lambda _: {'case_id': 'abort-case', 'inputs': ['hello', 'abort', 'never']},
        judge_provider=judge, track_files=False, allow_local=False, trace_evidence=capture, max_steps=3)
    files = Artifacts(output, environ={})
    case = run_case(run)
    files.save('case.json', case)
    session = AgentSession()
    async def invoke(payload, folder, shared_provider):
        files = Artifacts(folder, environ={})
        files.save('request.json', {'schema': 'abb.invocation.v1', 'run_id': uuid4().hex,
            'session_id': run.run_id, 'agent_id': 'abort-fixture', 'framework': 'acp', 'input': payload})
        await execute(repo, folder / 'request.json', folder, provider=shared_provider, session=session)
        return json.loads((folder / 'result.json').read_text())
    try:
        summary = await drive_run(run, invoke, output, provider=provider)
        last = json.loads((output / 'inputs/0002/result.json').read_text())
        validate_input_prefix(case, summary, last)
        assert summary['judge'] == 'received' and summary['otel'] == 'complete'
        assert summary['execution'] == 'failed' and len(summary['steps']) == 2
        assert last['raw_output']['partial_text'] == '2:abort'
        assert not (output / 'inputs/0003').exists()
        files.save('verification.json', {'status': 'passed', 'sdk_version': version('kuma-defuzex'),
            'production_services_called': False, 'provider_mode': 'offline-custom',
            'native_transport': 'real ACP stdio subprocess', 'unexecuted_inputs': summary['unexecuted_inputs']})
    finally:
        await session.aclose()
        provider.shutdown()
        if run.state in ('ready', 'input_delivered'):
            run.cancel()


if __name__ == '__main__':
    asyncio.run(main(Path(sys.argv[1])))
