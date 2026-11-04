"""Offline container acceptance: real ACP and MCP peers, SDK trace and Judge."""
import asyncio
import json
import sys
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from kuma import create_run
from kuma.otel import configure_trace_evidence
from opentelemetry.sdk.trace import TracerProvider
from agentbench.runtime.agentcontainer.session import AgentSession
from agentbench.runtime.agentcontainer.worker import execute
from agentbench.sdk.plugin.kuma.runner import drive_run
from agentbench.sdk.plugin.kuma.compatibility import run_case
from agentbench.sdk.common.artifacts import Artifacts


def tool_result(evidence, call_id):
    span = next(item for item in evidence['spans']
                if item['attributes'].get('gen_ai.tool.call.id') == call_id)
    value = span['attributes']['gen_ai.tool.call.result']
    return json.loads(value) if isinstance(value, str) else value


def report_judge_errors(callback):
    def wrapped(context):
        try:
            return callback(context)
        except Exception as exc:
            print('Offline Judge callback failed:', type(exc).__name__, str(exc), flush=True)
            raise
    return wrapped


async def main(output):
    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='abb-terminal-') as temporary:
        repo = Path(temporary)
        server = Path(__file__).resolve().parents[1] / 'acp_fixtures/server.py'
        mcp_server = Path(__file__).resolve().parents[1] / 'acp_fixtures/mcp_server.py'
        (repo / 'agent.toml').write_text(
            'agent_id="acp-mcp-terminal-fixture"\nframework="acp"\n'
            '[runtime]\ntimeout_sec=10\n'
            '[adapter]\ntype="acp"\ncwd=' + json.dumps(str(repo)) + '\ncommand='
            + json.dumps([sys.executable, str(server)]) + '\n'
            '[[adapter.mcp_servers]]\nname="echo"\ncommand=' + json.dumps(sys.executable)
            + '\nargs=' + json.dumps([str(mcp_server)]) + '\nenv_keys=[]\n')
        (repo / 'requirement.md').write_text(
            '---\nagent_description: Use supplied MCP tools and report observed command results.\n'
            'input_type: text\n---\n'
            '## Production Use Scenario\nA task that uses local commands and a configured MCP server.\n'
            '## Behaviors to Test\nUse the provided terminal and MCP tool, then report their observed results.\n'
            '## Known Limitations or Prohibited Behaviors\nNo external services.\n')
        provider = TracerProvider()
        capture = configure_trace_evidence(provider)
        checked = []
        @report_judge_errors
        def judge(context):
            for history, call, expected, code, source in zip(context.history,
                    ['terminal-tool', 'meta-tool'], ['SQL syntax error\n', 'first\nsecond\n'],
                    [7, 143], ['client_observed', 'agent_reported']):
                evidence = history.submission.extensions['trace_evidence']
                terminal = tool_result(evidence, call)[0]
                assert terminal['output'] == expected
                assert terminal['exitStatus']['exitCode'] == code
                assert terminal['source'] == source
                assert 'trace_event_limit' not in evidence['reasons']
                checked.append(call)
            mcp_evidence = context.history[2].submission.extensions['trace_evidence']
            mcp_result = tool_result(mcp_evidence, 'mcp-fixture-call')
            assert mcp_result['content'][0]['text'] == 'MCP tool invoked'
            checked.append('mcp-fixture-call')
            assert len(checked) == 3
            verdict = {'status': 'pass', 'issues': [],
                       'summary': 'Offline custom Judge verified terminal evidence and the result of a real stdio MCP tool call.'}
            files.save('judge.json', verdict)
            return verdict
        run = create_run(repo_path=repo, agent_profile_path=repo / 'requirement.md',
            case_provider=lambda _: {'case_id': 'acp-mcp-case',
                'inputs': ['terminal-reference', 'terminal-meta', 'mcp-call']},
            judge_provider=judge, track_files=False, allow_local=True, trace_evidence=capture, max_steps=3)
        files = Artifacts(output, environ={})
        files.save('case.json', run_case(run))
        session = AgentSession()
        async def invoke(payload, folder, shared_provider):
            Artifacts(folder, environ={}).save('request.json', {'schema': 'abb.invocation.v1',
                'run_id': uuid4().hex, 'session_id': run.run_id,
                'agent_id': 'acp-mcp-terminal-fixture', 'framework': 'acp', 'input': payload})
            await execute(repo, folder / 'request.json', folder, provider=shared_provider, session=session)
            return json.loads((folder / 'result.json').read_text())
        try:
            summary = await drive_run(run, invoke, output, provider=provider)
            files.save('summary.json', summary)
            assert summary['judge'] == 'received' and summary['otel'] == 'complete', summary
            assert summary['execution'] == 'succeeded' and len(summary['steps']) == 3
            files.save('verification.json', {'status': 'passed', 'sdk_version': version('kuma-defuzex'),
                'production_services_called': False, 'network': 'none', 'provider_mode': 'offline-custom',
                'native_transport': 'real ACP stdio subprocess',
                'mcp_transport': 'real stdio MCP subprocess', 'judge_checked': checked})
            print('Judge received terminal evidence and MCP tool output for:', ', '.join(checked), flush=True)
        finally:
            await session.aclose()
            provider.shutdown()
            if run.state in ('ready', 'input_delivered'):
                run.cancel()


if __name__ == '__main__':
    asyncio.run(main(Path(sys.argv[1])))
