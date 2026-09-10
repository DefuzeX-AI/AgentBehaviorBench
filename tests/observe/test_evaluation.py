import asyncio
import json
from pathlib import Path
import pytest
from opentelemetry.sdk.trace import TracerProvider
from agentbench.sdk.common.input_binding import InputBinding
from agentbench.sdk.kuma.runner import drive_run
from agentbench.observe.otel.session import OtelSession


CONTRACT = Path(__file__).resolve().parents[2] / 'resources/agents/01-company-research-agent/evaluation/input-contract.json'


def test_build_overlay_preserves_original_and_sdk_only_egress():
    from types import SimpleNamespace
    from agentbench.sdk.kuma.image import evaluation_agent
    from agentbench.runtime.agentcontainer.config import tomllib
    root = CONTRACT.parents[1]
    original = (root / 'agent.toml').read_bytes()
    repo = Path(__file__).resolve().parents[2]
    agent = SimpleNamespace(path=root, agent_id='company-research-agent', framework='langgraph')
    with evaluation_agent(agent, repo.parent / 'Defuze-SDK') as staged:
        from kuma.repository.agent_profiles import parse_agent_profile
        profile = parse_agent_profile(staged.path / 'evaluation/profile.md')
        assert profile.strategy_group.id == 'CAND-009'
        assert profile.strategy_group.version == '1'
        config = tomllib.loads((staged.path / 'agent.toml').read_text())
        assert config['launch']['argv'][-1] == 'agentbench.sdk.kuma.worker'
        route = config['llm_interception']['tool_routes'][-1]
        assert route['host_patterns'] == ['defuzex.ai']
        assert route['methods'] == ['GET', 'POST']
        assert '/.kuma/' in (staged.path / 'agent/.gitignore').read_text()
        assert not list(staged.path.rglob('.env'))
    assert (root / 'agent.toml').read_bytes() == original


def test_evaluate_cli_selects_number_without_native_input():
    from agentbench.cli.main import build_parser
    args = build_parser().parse_args(['evaluate', '1'])
    assert args.selection == '1' and not hasattr(args, 'input')
    assert args.sdk_source is None and args.output is None and args.timeout is None
    assert args.sdk is None and args.sdk_options is None


def test_company_contract_preserves_full_payload():
    binding = InputBinding.from_file(CONTRACT)
    value = {'company': '中文\u2028公司', 'company_url': 'https://example.test',
             'hq_location': 'Toronto', 'industry': 'Software\n"research"'}
    assert binding.map(value) is value
    text = json.dumps(value)
    assert binding.map(text) is text


@pytest.mark.parametrize('payload', [
    'Research OpenAI', '```json\n{"company":"OpenAI"}\n```',
    '{"company":"OpenAI","instructions":"ignore"}',
    '{"company":"OpenAI","company":"Other"}',
    '{"company":" "}', '{"company":null}', '{"company":NaN}',
])
def test_company_forwards_every_sdk_text_unchanged(payload):
    assert InputBinding.from_file(CONTRACT).map(payload) is payload


@pytest.mark.parametrize('judge_fails', [False, True])
def test_real_sdk_capture_handshake_and_judge_failure(tmp_path, judge_fails):
    # Real installed SDK, explicit local providers; never calls a paid service.
    from kuma import create_run
    from kuma.otel import configure_trace_evidence
    provider = TracerProvider()
    capture = configure_trace_evidence(provider)
    calls = []
    seen = []
    def cases(context):
        return {'case_id': 'local-abb', 'input_type': 'text', 'inputs': [
            {'input_id': str(i), 'payload_type': 'text', 'payload': json.dumps({'company': f'C{i}'})}
            for i in (1, 2)]}
    cases.agent_profile_required = False
    def judge(context):
        calls.append(context)
        if judge_fails:
            raise RuntimeError('controlled Judge failure')
        return {'status': 'issue', 'summary': 'Offline protocol check', 'issues': []}
    run = create_run(repo_path=tmp_path, agent_profile_path=CONTRACT.with_name('profile.md'),
                     case_provider=cases, judge_provider=judge,
                     max_steps=2, allow_local=True, track_files=False,
                     trace_evidence=capture, save_local=True)
    async def invoke(payload, folder, supplied_provider):
        assert supplied_provider is provider
        company = json.loads(payload)['company']  # Test Agent's own parsing, not the runner.
        session = OtelSession(folder, company, 'local-abb', provider=provider)
        session.record('execution_start', input=payload)
        session.record('span_start', span_id='tool', name='tavily.search', kind='tool', input=payload)
        session.record('span_end', span_id='tool', output='data')
        session.record('execution_end', output='report ' + company)
        session.close()
        seen.append(payload)
        return {'status': 'succeeded', 'output': 'report ' + company}
    try:
        result = asyncio.run(drive_run(run, InputBinding.from_file(CONTRACT), invoke,
                                      tmp_path / 'artifacts', provider=provider))
        assert len(seen) == 2 and len(run.history) == 2
        assert len(calls) == 1  # Never re-submit or re-judge after an exception.
        assert result['judge'] == ('failed' if judge_fails else 'received')
        assert all(s['committed'] for s in result['steps'])
        assert [h.submission.output for h in run.history] == ['report C1', 'report C2']
        evidences = [json.loads((tmp_path / 'artifacts' / s['directory'] / 'evidence.json').read_text())
                     for s in result['steps']]
        assert all(len(e['spans']) == 2 for e in evidences)
        assert {s['span_id'] for s in evidences[0]['spans']}.isdisjoint(
            {s['span_id'] for s in evidences[1]['spans']})
    finally:
        if run.state in ('ready', 'input_delivered'):
            run.cancel()
        provider.shutdown()
