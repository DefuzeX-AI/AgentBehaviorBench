"""The local SDK plugin: fixed Cases and a local Judge through the real KUMA wheel, offline."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentbench.harness.errors import ProviderSelectionError
from agentbench.sdk.common.artifacts import Artifacts
from agentbench.sdk.common.case_identity import case_content_sha256
from agentbench.sdk.plugin.local import relay as relay_module
from agentbench.sdk.plugin.local.cases import CONVERSATIONS, FixedCase, case_content
from agentbench.sdk.plugin.local.judge import REQUEST, RESPONSE, LocalJudge, verdict_fields
from agentbench.sdk.plugin.local.relay import JudgeModel, JudgeRelay, ask_model, json_object, judge_model
from agentbench.sdk.plugins import resolve_sdk

KEY = 'sk-local-judge-test-secret'
MODEL_ENV = {'OPENROUTER_API_KEY': KEY, 'OPENROUTER_MODEL': 'glm-test',
             'OPENROUTER_BASE_URL': 'https://open.bigmodel.cn/api/coding/paas/v4'}


def passing(model, steps):
    return verdict_fields({'status': 'pass', 'confidence': 'high', 'reason': 'Coherent.'},
                          {step['input_id'] for step in steps}), '{"status": "pass"}'


@pytest.fixture
def offline_repo(tmp_path, monkeypatch):
    """A Run repository where any KUMA Backend call would fail immediately."""
    runtime = tmp_path / 'xdg'
    runtime.mkdir(mode=0o700)
    monkeypatch.setenv('XDG_RUNTIME_DIR', str(runtime))
    for name in ('KUMA_API_KEY', 'DEFUZEX_API_KEY'):
        monkeypatch.delenv(name, raising=False)
    # Nor may a key stored by kuma.configure() stand in for the missing one.
    monkeypatch.setenv('KUMA_CONFIG_HOME', str(tmp_path / 'no-stored-key'))
    monkeypatch.setenv('KUMA_BASE_URL', 'https://127.0.0.1:9')
    repo = tmp_path / 'repo'
    repo.mkdir()
    (repo / 'agent.py').write_text("print('agent')\n")
    return repo


def generate(repo, tmp_path, count):
    from kuma import create_run
    from agentbench.sdk.plugin.kuma.generation import generate_collection
    from agentbench.sdk.plugin.local.worker import LocalProviders

    providers = LocalProviders()
    return generate_collection(
        create_run, count=count, files=Artifacts(tmp_path / 'generated'), repo=repo,
        options={'repo_path': repo, 'allow_local': True, 'track_files': False,
                 'max_steps': providers.max_steps},
        case_options=providers.case_options)


def execute(repo, artifact, judge, *, fail_first=False):
    from kuma import create_run
    from kuma.otel import configure_trace_evidence
    from opentelemetry.sdk.trace import TracerProvider

    provider = TracerProvider()
    tracer = provider.get_tracer('local-sdk-test')
    run = create_run(repo_path=repo, allow_local=True, track_files=False, case_path=artifact,
                     trace_evidence=configure_trace_evidence(provider), judge_provider=judge)
    while (item := run.get_input(full=True)) is not None:
        with tracer.start_as_current_span('abb.execute'):
            output = f'Reply to {item.payload}'
        provider.force_flush()
        if fail_first:
            run.submit(status='failed', error='Agent execution failed; see local diagnostics')
        else:
            run.submit(output=output, status='completed')
    return run


def test_local_is_discovered_beside_kuma_and_selected_by_name():
    selection = resolve_sdk('local')
    assert selection.reference.name == 'local'
    assert selection.value.execution == 'container'
    assert resolve_sdk('kuma').reference.name == 'kuma'


def test_fixed_cases_are_distinct_and_respect_the_step_limit():
    cases = [case_content(index) for index in range(2 * len(CONVERSATIONS) + 1)]
    assert len({case['case_id'] for case in cases}) == len(cases)
    assert len({case_content_sha256(case) for case in cases}) == len(cases)
    assert [item['input_id'] for item in cases[0]['inputs']] == ['step-1', 'step-2', 'step-3']
    assert all(item['payload_type'] == 'text' for case in cases for item in case['inputs'])
    assert len(FixedCase(0).generate_case(SimpleNamespace(max_steps=2))['inputs']) == 2
    with pytest.raises(ValueError):
        case_content(-1)
    with pytest.raises(ValueError):
        case_content(0, 0)


def test_generation_and_judging_need_no_backend_or_kuma_credential(offline_repo, tmp_path):
    from agentbench.sdk.plugin.kuma.compatibility import artifact_case, run_case

    collection = generate(offline_repo, tmp_path, 4)
    entries = collection['cases']
    assert [entry['case_id'] for entry in entries] == [f'local-smoke-v1-0{i}' for i in range(1, 5)]
    assert len({entry['content_sha256'] for entry in entries}) == 4
    assert {entry['origin'] for entry in entries} == {'custom'}

    seen = []

    def ask(model, steps):
        seen.append(steps)
        return passing(model, steps)

    run_directory = tmp_path / 'run'
    (run_directory / 'evaluation').mkdir(parents=True)
    relay = JudgeRelay(run_directory, JudgeModel('https://judge.invalid/v1', 'judge-test', KEY),
                       environ={'ABB_LOCAL_JUDGE_API_KEY': KEY}, ask=ask, interval=0.02).start()
    try:
        run = execute(offline_repo, entries[0]['artifact'],
                      LocalJudge(run_directory / 'evaluation', timeout=10, interval=0.02))
    finally:
        relay.stop()

    report = run.report
    assert report.status == 'pass' and report.confidence == 'high'
    assert report.extensions['case_id'] == run.case_id == 'local-smoke-v1-01'
    assert report.extensions['decided_by'] == 'model'
    assert [step['trace_spans'] for step in report.extensions['steps']] == [1, 1, 1]
    assert [step['input_id'] for step in seen[0]] == ['step-1', 'step-2', 'step-3']
    assert seen[0][0]['output'] == f"Reply to {CONVERSATIONS[0][0]}"
    # The executed Case is the prepared one, as the worker and the host verify.
    artifact = json.loads((offline_repo / entries[0]['artifact']).read_text())
    assert case_content_sha256(run_case(run)) == entries[0]['content_sha256']
    assert case_content_sha256(artifact_case(artifact)) == entries[0]['content_sha256']
    record = (run_directory / 'local-judge.json').read_text()
    assert json.loads(record)['answer']['status'] == 'pass' and KEY not in record


def test_failed_steps_are_judged_without_the_host(offline_repo, tmp_path):
    entries = generate(offline_repo, tmp_path, 1)['cases']
    evaluation = tmp_path / 'evaluation'
    evaluation.mkdir()
    run = execute(offline_repo, entries[0]['artifact'], LocalJudge(evaluation, timeout=0.1),
                  fail_first=True)
    assert run.report.status == 'issue'
    assert run.report.extensions['decided_by'] == 'run_status'
    assert run.report.issues[0]['severity'] == 'high'
    assert not (evaluation / REQUEST).exists()


def test_missing_trace_evidence_is_insufficient_without_the_host(tmp_path):
    submission = {'input_id': 'step-1', 'status': 'completed', 'output': 'hello',
                  'extensions': {}, 'capture_status': {'traces': {'status': 'missing'}}}
    context = SimpleNamespace(case=SimpleNamespace(case_id='local-smoke-v1-01'), history=[
        SimpleNamespace(test_input={'payload': 'hi'}, submission=submission)])
    report = LocalJudge(tmp_path, timeout=0.1).judge(context)
    assert report['status'] == 'insufficient_evidence'
    assert report['evidence_gaps'][0]['input_id'] == 'step-1'
    assert not (tmp_path / REQUEST).exists()


def test_a_failed_model_call_fails_the_judgment_with_its_cause(offline_repo, tmp_path):
    from kuma.errors import ProviderError

    def unreachable(model, steps):
        raise RuntimeError('HTTP 429 from https://judge.invalid/v1/chat/completions: rate limited')

    entries = generate(offline_repo, tmp_path, 1)['cases']
    run_directory = tmp_path / 'run'
    (run_directory / 'evaluation').mkdir(parents=True)
    relay = JudgeRelay(run_directory, JudgeModel('https://judge.invalid/v1', 'judge-test', KEY),
                       ask=unreachable, interval=0.02).start()
    try:
        with pytest.raises(ProviderError, match='HTTP 429'):
            execute(offline_repo, entries[0]['artifact'],
                    LocalJudge(run_directory / 'evaluation', timeout=10, interval=0.02))
    finally:
        relay.stop()
    assert 'error' in json.loads((run_directory / 'evaluation' / RESPONSE).read_text())


def test_the_judge_waits_only_as_long_as_configured(tmp_path):
    from kuma.errors import ProviderError

    judge = LocalJudge(tmp_path, timeout=0.05, interval=0.01)
    with pytest.raises(ProviderError, match='answered no local Judge request'):
        judge.ask_host({'schema': 'abb.local_judge.request.v1', 'steps': []}, set())


def test_model_replies_are_read_leniently_but_must_decide():
    assert json_object('```json\n{"status": "pass"}\n```') == {'status': 'pass'}
    assert json_object('Verdict: {"status": "issue"} done')['status'] == 'issue'
    with pytest.raises(ValueError):
        json_object('no verdict')
    with pytest.raises(ValueError):
        verdict_fields({'status': 'maybe'}, set())
    issue = verdict_fields({'status': 'issue', 'confidence': 'certain', 'reason': 'Step 2 is empty.',
                            'issues': [{'input_id': 'unknown', 'message': 'empty'}]}, {'step-2'})
    assert issue['confidence'] == 'medium'
    assert issue['issues'] == [{'severity': 'medium', 'message': 'empty'}]
    assert verdict_fields({'status': 'issue', 'reason': 'Off topic.'}, set())['issues'][0]['message'] == 'Off topic.'


def test_judge_model_defaults_to_the_agent_target_and_accepts_overrides():
    model = judge_model(MODEL_ENV)
    assert (model.base_url, model.model, model.api_key) == (
        MODEL_ENV['OPENROUTER_BASE_URL'], 'glm-test', KEY)
    assert KEY not in repr(model)
    override = judge_model({**MODEL_ENV, 'ABB_LOCAL_JUDGE_MODEL': 'judge-only'})
    assert override.model == 'judge-only' and override.api_key == KEY
    local = judge_model({'ABB_LOCAL_JUDGE_BASE_URL': 'http://127.0.0.1:8000/v1/',
                         'ABB_LOCAL_JUDGE_MODEL': 'local', 'ABB_LOCAL_JUDGE_API_KEY': 'x'})
    assert local.base_url == 'http://127.0.0.1:8000/v1'


@pytest.mark.parametrize('environ, message', [
    ({**MODEL_ENV, 'OPENROUTER_BASE_URL': 'https://open.bigmodel.cn/api/anthropic/v1'}, 'Anthropic'),
    ({**MODEL_ENV, 'ABB_LOCAL_JUDGE_BASE_URL': 'http://judge.example/v1'}, 'HTTPS'),
    ({key: value for key, value in MODEL_ENV.items() if key != 'OPENROUTER_API_KEY'}, 'OPENROUTER_API_KEY'),
    ({}, 'OPENROUTER_MODEL'),
])
def test_judge_model_rejects_unusable_endpoints(environ, message):
    with pytest.raises(ValueError, match=message):
        judge_model(environ)


def test_ask_model_posts_openai_chat_and_retries_a_rate_limit(monkeypatch):
    received = []
    replies = [(429, {'error': {'code': '1302', 'message': 'rate limited'}}),
               (200, {'choices': [{'message': {'content': (
                   '```json\n{"status": "issue", "confidence": "high", "reason": "Step 2 is off topic.", '
                   '"issues": [{"input_id": "step-2", "message": "Talks about weather."}]}\n```')}}]})]

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['content-length'])))
            received.append((self.path, self.headers['authorization'], body))
            status, reply = replies.pop(0)
            payload = json.dumps(reply).encode()
            self.send_response(status)
            self.send_header('content-type', 'application/json')
            self.send_header('content-length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    monkeypatch.setattr(relay_module.time, 'sleep', lambda seconds: None)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        model = JudgeModel(f'http://127.0.0.1:{server.server_port}/v1', 'glm-test', KEY)
        steps = [{'input_id': 'step-1', 'input': 'Hi', 'output': 'Hello'},
                 {'input_id': 'step-2', 'input': 'Summarize', 'output': 'Sunny today'}]
        verdict, reply = ask_model(model, steps)
    finally:
        server.shutdown()
    assert verdict['status'] == 'issue'
    assert verdict['issues'] == [{'severity': 'medium', 'message': 'Talks about weather.', 'input_id': 'step-2'}]
    assert 'Step 2 is off topic.' in reply
    path, authorization, body = received[-1]
    assert len(received) == 2 and path == '/v1/chat/completions'
    assert authorization == f'Bearer {KEY}' and body['model'] == 'glm-test'
    assert json.loads(body['messages'][1]['content']) == {'steps': steps}


def test_overlay_forwards_no_kuma_setting_and_admits_no_backend(tmp_path):
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib
    from agentbench.sdk.plugin.kuma.image import evaluation_agent
    from agentbench.sdk.plugin.local.benchmark import OVERLAY

    root = tmp_path / 'unit'
    (root / 'agent').mkdir(parents=True)
    (root / 'Dockerfile').write_text('FROM python:3.13-slim\nUSER agent\n')
    (root / 'agent.toml').write_text('agent_id = "echo"\n[runtime]\ntype = "docker"\n'
                                     'env_keys = ["OPENAI_BASE_URL"]\n[launch]\nargv = ["python", "app.py"]\n')
    agent = SimpleNamespace(path=root, agent_id='echo', framework='langgraph')
    with evaluation_agent(agent, **OVERLAY) as staged:
        manifest = tomllib.loads((staged.path / 'agent.toml').read_text())
        dockerfile = (staged.path / 'Dockerfile').read_text()
    assert manifest['launch']['argv'] == ['python', '-m', 'agentbench.sdk.plugin.local.worker']
    assert manifest['runtime']['env_keys'] == ['OPENAI_BASE_URL']
    hosts = {host for route in manifest['llm_interception']['tool_routes'] for host in route['host_patterns']}
    assert hosts == {'api.github.com'}
    assert 'requirement.md' not in dockerfile
    (root / 'requirement.md').write_text('An echo Agent.\n')
    with evaluation_agent(agent, **OVERLAY) as staged:
        assert 'COPY requirement.md' in (staged.path / 'Dockerfile').read_text()


def test_kuma_still_requires_its_key_while_local_evaluation_does_not(tmp_path, monkeypatch):
    from agentbench.sdk.plugin.kuma import service
    from agentbench.sdk.plugin.local.benchmark import OVERLAY

    agent = SimpleNamespace(agent_id='echo', path=tmp_path / 'unit', framework='langgraph')
    with pytest.raises(ValueError, match='KUMA_API_KEY'):
        service.evaluate(agent, output=tmp_path / 'kuma', environ={})

    overlays = []

    def stop_before_docker(agent, **options):
        overlays.append(options)
        raise RuntimeError('stopped before the image build')

    monkeypatch.setattr(service, 'evaluation_agent', stop_before_docker)
    with pytest.raises(RuntimeError, match='before the image build'):
        service.evaluate(agent, output=tmp_path / 'local', environ={}, require_credentials=False,
                         overlay=OVERLAY)
    assert overlays[0]['backend'] is None and overlays[0]['worker_package'] == 'agentbench.sdk.plugin.local'
    status = json.loads(next((tmp_path / 'local').glob('*/run.json')).read_text())
    assert status['status'] == 'failed'


def test_local_runner_validates_both_models_before_building(tmp_path):
    from agentbench.sdk.plugin.local.benchmark import LocalContainerRunner

    registration = SimpleNamespace(agent_id='echo', path=tmp_path, case_count=1)
    with pytest.raises(ProviderSelectionError, match='OPENROUTER_MODEL'):
        LocalContainerRunner(environ={}).validate_sdk(registration)
    runner = LocalContainerRunner(environ=MODEL_ENV)
    # No KUMA key and no requirement.md are needed.
    assert runner.validate_sdk(registration) == 'local-container'
    assert runner.recovery_capabilities(SimpleNamespace(path=tmp_path)).resume_judgment is False


def test_local_runner_relays_the_judge_only_while_a_case_executes(tmp_path, monkeypatch):
    from agentbench.sdk.plugin.local import benchmark

    calls = []

    def container(registration, **options):
        calls.append(options)
        directory = tmp_path / f'run-{len(calls)}'
        (directory / 'evaluation').mkdir(parents=True)
        options['on_artifacts_ready'](directory)
        if options.get('case_artifact') is not None:
            # Stand in for the worker's Judge inside the container.
            judge = LocalJudge(directory / 'evaluation', timeout=10, interval=0.02)
            calls.append(judge.ask_host({'schema': 'abb.local_judge.request.v1', 'case_id': 'c',
                                         'steps': [{'input_id': 'step-1', 'input': 'Hi', 'output': 'Hello'}]},
                                        {'step-1'}))
        return directory

    monkeypatch.setattr(benchmark, 'evaluate', container)
    monkeypatch.setattr(benchmark, 'JudgeRelay', lambda directory, model, environ=None: JudgeRelay(
        directory, model, environ=environ, ask=passing, interval=0.02))
    runner = benchmark.LocalContainerRunner(environ=MODEL_ENV)
    registration = SimpleNamespace(agent_id='echo', path=tmp_path, case_count=1)
    runner._evaluate(registration, generation_count=1, on_artifacts_ready=lambda path: None)
    assert calls[0]['require_credentials'] is False and calls[0]['overlay'] is benchmark.OVERLAY
    assert not (tmp_path / 'run-1' / 'local-judge.json').exists()

    ready = []
    runner._evaluate(registration, case_artifact=Path('case.json'), on_artifacts_ready=ready.append)
    assert ready == [tmp_path / 'run-2'] and calls[-1]['status'] == 'pass'
    assert json.loads((tmp_path / 'run-2' / 'local-judge.json').read_text())['model'] == 'glm-test'
