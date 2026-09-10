"""OFFLINE acceptance only: real SDK + Company + OTel, local Case/Judge providers."""
import asyncio
import json
from pathlib import Path
from kuma import create_run
from kuma.otel import configure_trace_evidence
from opentelemetry.sdk.trace import TracerProvider
from agentbench.sdk.kuma.runner import drive_run
from agentbench.sdk.common.input_binding import InputBinding
from agentbench.runtime.agentcontainer.worker import execute
from company_upstream import install


async def main():
    install()
    root, out = Path('/opt/agent'), Path('/run/abb-output')
    assert not __import__('os').access(root / 'agent/backend/graph.py', __import__('os').W_OK)
    provider = TracerProvider()
    capture = configure_trace_evidence(provider)
    def cases(context):
        return {'case_id': 'offline-company-sdk', 'input_type': 'text', 'inputs': [
            {'input_id': 'one', 'payload_type': 'text', 'payload': 'OpenAI'}]}
    def judge(context):
        assert len(context.history) == 1
        submission = context.history[0].submission
        assert 'OFFLINE REPORT' in submission.output
        assert len(submission.extensions['trace_evidence']['spans']) > 10
        return {'status': 'pass', 'summary': 'OFFLINE local protocol acceptance, not official Judge', 'issues': []}
    run = create_run(repo_path=root / 'agent', agent_profile_path=root / 'evaluation/profile.md',
                     case_provider=cases, judge_provider=judge, max_steps=1,
                     allow_local=False, track_files=False, save_local=True, trace_evidence=capture)
    async def invoke(payload, folder, shared_provider):
        request = folder / 'request.json'
        request.write_text(json.dumps({'schema': 'abb.invocation.v1', 'run_id': 'offline-company',
            'agent_id': 'company-research-agent', 'framework': 'langgraph', 'input': payload}))
        await execute(root, request, folder, provider=shared_provider)
        return json.loads((folder / 'result.json').read_text())
    try:
        summary = await drive_run(run, InputBinding({'encoding': 'identity'}), invoke, out, provider=provider)
        assert summary['judge'] == 'received', summary
        assert summary['otel'] == 'complete', summary
        assert summary['evidence'] == 'captured', summary
        print('OFFLINE SDK + original Company + OTel + local Judge passed')
    finally:
        if run.state in ('ready', 'input_delivered'):
            run.cancel()
        provider.shutdown()


if __name__ == '__main__':
    asyncio.run(main())
