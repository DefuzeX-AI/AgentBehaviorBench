"""Offline container acceptance: real ACP target, worker, KUMA SDK and local Judge.

Run inside a prepared image with /app read-only and /artifacts writable. Network
must be disabled. This is not an official KUMA service verdict or H2 execution.
"""
import asyncio
import json
import sys
from importlib.metadata import version
from pathlib import Path

from kuma import create_run, to_json
from kuma.otel import configure_trace_evidence
from kuma.providers import OfficialJudgeProvider
from kuma.providers._official_evidence_upload import judge_upload_config
from opentelemetry.sdk.trace import TracerProvider

from agentbench.runtime.agentcontainer.session import AgentSession
from agentbench.runtime.agentcontainer.worker import execute
from agentbench.sdk.common.artifacts import Artifacts
from agentbench.sdk.plugin.kuma.compatibility import run_case
from agentbench.sdk.plugin.kuma.judge_bundle import export_context, restore_context
from agentbench.sdk.plugin.kuma.runner import drive_run
from tests.sdk_fixtures.issue_run import profile


def judge(context):
    for index, item in enumerate(context.history, 1):
        submission = item.submission
        expected = f'{index}:' + ('first' if index == 1 else 'second')
        assert submission.output == expected
        assert submission.extensions['agent_output_actor'] == 'target_agent'
        assessment = submission.extensions['assessment_evidence']
        assert assessment['coverage']['public_messages'] == 'complete'
        assert [m['content'] for m in assessment['public_messages']] == [expected]
    return {'status': 'pass', 'summary': 'Real captured ACP public text and attributed output', 'issues': []}


async def main():
    output = Path('/artifacts')
    files = Artifacts(output)
    root = Path('/tmp/assessment-target')
    (root / 'agent').mkdir(parents=True)
    (root / 'agent.toml').write_text(
        'agent_id="claim-capture-fixture"\nframework="acp"\n'
        '[adapter]\ntype="acp"\n'
        f'command=["{sys.executable}","/app/tests/acp_fixtures/server.py"]\n'
        f'cwd="{root / "agent"}"\n')
    provider = TracerProvider()
    capture = configure_trace_evidence(provider)
    run = create_run(repo_path=root / 'agent', agent_profile_path=profile(root / 'agent'),
        case_provider=lambda _: {'case_id': 'claim-capture-fixture', 'inputs': ['first', 'second']},
        judge_provider=judge, allow_local=True, max_steps=2, trace_evidence=capture,
        track_files=False)
    session = AgentSession()
    files.save('case.json', run_case(run))
    async def invoke(payload, folder, shared_provider):
        request = folder / 'request.json'
        Artifacts(folder).save('request.json', {
            'schema': 'abb.invocation.v1', 'run_id': folder.name,
            'session_id': run.run_id, 'agent_id': 'claim-capture-fixture',
            'framework': 'acp', 'input': payload})
        assert await execute(root, request, folder, provider=shared_provider, session=session) == 0
        return json.loads((folder / 'result.json').read_text())
    try:
        summary = await drive_run(run, invoke, output, provider=provider)
        assert summary['judge'] == 'received' and run.report.status == 'pass'
        context = restore_context(export_context(run, run_case(run)))
        config = judge_upload_config({
            'allowed_extensions': ['.json'], 'max_files': 20,
            'max_file_bytes': 5 * 1024 * 1024, 'max_total_bytes': 8 * 1024 * 1024,
            'manifest_schema_version': '1',
            'supported_assessment_contracts': ['kuma.judge_assessment.v1'],
            'evidence_types': ['raw_log', 'defuzex.runtime_evidence.capabilities.v1',
                               'defuzex.assessment_evidence.v1'],
            'runtime_evidence_capabilities': ['runtime_evidence', 'agent_output', 'runtime_trace']})
        # Local SDK projection only; this object has no HTTP transport.
        upload = OfficialJudgeProvider(object())._prepare_upload(context, config)
        for part in upload.log_parts:
            files.save('prepared-wire/' + part.filename, json.loads(part.data))
        files.save('agent-output.json', [item.submission.output for item in run.history])
        files.save('verification.json', {
            'status': 'passed', 'kuma_version': version('kuma-defuzex'),
            'acp_version': version('agent-client-protocol'), 'network': 'disabled_by_docker',
            'agent': 'deterministic ACP fixture, not LangREPL', 'judge': 'local assertion Judge',
            'official_service_judgment': False, 'paid_calls': 0,
            'public_message_parts': sum('assessment' in part.filename for part in upload.log_parts),
            'history_items': len(run.history), 'report': to_json(run.report)})
    finally:
        await session.aclose()
        provider.shutdown()
    print('Container claim-evidence acceptance passed:', output, flush=True)


if __name__ == '__main__':
    asyncio.run(main())
