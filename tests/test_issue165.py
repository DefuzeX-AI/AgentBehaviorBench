"""Future Case isolation, durable artifacts, and original telemetry transport."""
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentbench.sdk.integration.artifacts import FileArtifactStore
from agentbench.sdk.integration.context import ExecutionChannel
from agentbench.runtime.docker.execution_policy import AgentExecutionPolicy
from agentbench.sdk.plugin.kuma.service import EvaluationPolicy


def test_case_is_durable_and_attempts_do_not_replace_history(tmp_path):
    store = FileArtifactStore(tmp_path / 'suite')
    case = store.case('agent', 0)
    case.publish_case(b'{"case":"one"}')
    first = case.attempt('first')
    first.write_json('steps/0001/result.json', {'status': 'failed'})
    second = case.attempt('second')
    second.write_json('steps/0001/result.json', {'status': 'succeeded'})
    reopened = FileArtifactStore(store.directory).case('agent', 0)
    assert (reopened.directory / 'case.json').read_bytes() == b'{"case":"one"}'
    assert json.loads((first.directory / 'steps/0001/result.json').read_text())['status'] == 'failed'
    with pytest.raises(ValueError, match='cannot be replaced'):
        case.publish_case(b'{"case":"other"}')


def test_artifact_paths_cannot_escape_or_follow_links(tmp_path):
    attempt = FileArtifactStore(tmp_path / 'suite').case('agent', 0).attempt('first')
    with pytest.raises(ValueError):
        attempt.write_json('../elsewhere.json', {})
    external = tmp_path / 'external'
    external.mkdir()
    (attempt.directory / 'link').symlink_to(external, target_is_directory=True)
    with pytest.raises(ValueError):
        attempt.write_json('link/secret.json', {})


def test_agent_mounts_never_include_case_ledger_or_result(tmp_path):
    channel = ExecutionChannel.create(tmp_path / 'channel')
    repository = tmp_path / 'workspace'
    repository.mkdir()
    ledger = tmp_path / 'result/sdk/.kuma'
    ledger.mkdir(parents=True)
    controller = EvaluationPolicy(ledger, repository=repository, target='/workspace', channel=channel)
    agent = AgentExecutionPolicy(repository, '/workspace', True, channel, tmp_path / 'agent-output')
    assert any(str(ledger.parent) in value for value in controller.run_arguments())
    assert all(str(ledger.parent) not in value for value in agent.run_arguments())
    assert any('target=/run/abb-channel/request,readonly' in value for value in agent.run_arguments())
    assert not (repository / '.kuma').exists()


def test_original_spans_reach_real_sdk_without_rewriting_identity(tmp_path):
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.resources import Resource
    from kuma.otel import configure_trace_evidence
    from agentbench.runtime.agentcontainer.telemetry import WireExporter
    from agentbench.sdk.integration.telemetry import decode_span
    from agentbench.sdk.plugin.kuma.integration import KumaEvidenceSink

    source = TracerProvider(resource=Resource({'service.name': 'abb-evaluation'}))
    wire = WireExporter()
    wire.destination = tmp_path / 'spans.jsonl'
    source.add_span_processor(SimpleSpanProcessor(wire))
    target = TracerProvider()
    capture = configure_trace_evidence(target)
    capture.begin_step('run-165', 'case-165', 'step-one')
    with source.get_tracer('agentbench.observe').start_as_current_span('chat') as span:
        span.set_attribute('gen_ai.operation.name', 'chat')
        span.set_attribute('gen_ai.input.messages', '[{"role":"user","content":"actual question"}]')
        span.set_attribute('gen_ai.output.messages', '[{"role":"assistant","content":"actual answer"}]')
    source.force_flush()
    restored = decode_span(json.loads(wire.destination.read_text()))
    assert restored.context.span_id == span.context.span_id
    assert restored.context.trace_id == span.context.trace_id
    assert restored.start_time == span.start_time and restored.end_time == span.end_time
    KumaEvidenceSink(capture).accept_span(restored)
    evidence = capture.prepare_step('run-165', 'case-165', 'step-one')
    assert 'actual question' in str(evidence)
    assert 'actual answer' in str(evidence)
    source.shutdown()
    target.shutdown()


@pytest.mark.skipif(not os.getenv('ABB_PRIVATE_STORAGE_ACCEPTANCE'), reason='Opt-in real Docker acceptance')
@pytest.mark.parametrize('framework,workspace', [('langgraph', True), ('langgraph', False), ('acp', True)])
def test_real_containers_keep_future_case_private(tmp_path, monkeypatch, framework, workspace):
    from agentbench.sdk.plugin.kuma import image
    from agentbench.runtime.docker import worker_build
    from agentbench.sdk.plugin.kuma.service import evaluate
    from agentbench.sdk.common.workspace import workspace_policy, prepare_workspace, workspace_digest
    from uuid import uuid4

    # Dependencies are preinstalled in this local image. No package downloads or
    # model/backend calls are used by this acceptance.
    monkeypatch.setattr(image, 'SDK_INSTALL', '')
    monkeypatch.setattr(image, 'append_whitelist', lambda source, *args: source)
    monkeypatch.setattr(worker_build, 'stage_adapter_dependencies', lambda *a: None)
    monkeypatch.setattr(worker_build, 'stage_runtime_dependencies', lambda *a: None)
    root = tmp_path / 'unit'
    (root / 'agent').mkdir(parents=True)
    (root / 'acceptance').mkdir()
    (root / 'acceptance/__init__.py').write_text('')
    fixture = Path(__file__).parent / 'sdk_fixtures/private_storage.py'
    (root / 'acceptance/worker.py').write_bytes(fixture.read_bytes())
    (root / 'agent/echo.py').write_text(
        'import json, os\nfrom pathlib import Path\n'
        'class Echo:\n'
        ' def __init__(self): self.turns=0\n'
        ' def invoke(self,value,config=None):\n'
        '  self.turns+=1\n'
        '  if self.turns==1:\n'
        '   paths=["/run/abb-sdk-storage", "/run/abb-output/case.json", "/opt/abb-sdk-repo/.kuma"]\n'
        '   assert not any(Path(p).exists() for p in paths), paths\n'
        '   assert not os.environ.get("KUMA_API_KEY")\n'
        '   work=Path("/home/agent/workspace")\n'
        '   if work.exists():\n'
        '    assert list(work.iterdir())==[]\n'
        '    (work/"agent.txt").write_text("agent change")\n'
        '   return "first step isolated"\n'
        '  return value\n'
        'graph=Echo()\n')
    (root / 'agent/server.py').write_bytes(
        (Path(__file__).parent / 'sdk_fixtures/private_storage_acp.py').read_bytes())
    (root / 'agent/langgraph.json').write_text('{"graphs":{"echo":"echo.py:graph"}}')
    manifest = (
        'agent_id="private-storage-acceptance"\nframework="langgraph"\n'
        '[runtime]\ntype="docker"\ntimeout_sec=45\nenv_keys=[]\n'
        '[build]\ncontext="."\ndockerfile="Dockerfile"\n'
        '[launch]\nargv = ["python","-m","acceptance.worker"]\nworkdir="/opt/agent"\n'
        '[adapter]\ntype="langgraph"\nconfig="langgraph.json"\ngraph_id="echo"\n')
    if workspace:
        manifest += ('[evaluation.workspace]\npath="/home/agent/workspace"\ninitial_state="empty"\n'
                     '[evaluation.file_evidence]\ntrack_files=true\nupload_diff=true\n')
    if framework == 'acp':
        manifest = manifest.replace('framework="langgraph"', 'framework="acp"').replace(
            'type="langgraph"\nconfig="langgraph.json"\ngraph_id="echo"',
            'type="acp"\ncommand=["python","/opt/agent/agent/server.py"]\ncwd="/home/agent/workspace"')
    (root / 'agent.toml').write_text(manifest)
    (root / 'Dockerfile').write_text(
        'FROM abb-campaign-validation:local\nWORKDIR /opt/agent\n'
        'ENV PYTHONPATH=/opt/abb-runtime:/opt/agent\n'
        'COPY .abb-runtime/ /opt/abb-runtime/\n'
        'COPY agent/ ./agent/\nCOPY acceptance/ /opt/abb-sdk-runtime/acceptance/\n'
        'COPY agent.toml ./\nUSER agent\n')
    descriptor = SimpleNamespace(path=root, agent_id='private-storage-acceptance', framework=framework)
    output = Path(__file__).parents[1] / 'results/verification' / ('issue165-' + uuid4().hex)
    store = FileArtifactStore(output / 'suite')
    options = dict(output=output, environ={}, timeout=120, require_credentials=False,
                   artifact_store=store,
                   overlay={'backend': None, 'worker_package': 'acceptance',
                            'sdk_environment': (), 'require_profile': False})
    generation = evaluate(descriptor, generation_count=1, **options)
    collection = json.loads((generation / 'case-collection.json').read_text())
    entry = collection['cases'][0]
    case_file = store.case(descriptor.agent_id, 0).directory / 'case.json'
    assert case_file.read_bytes() == (generation / 'cases' / Path(entry['artifact']).name).read_bytes()
    contract = None
    if workspace:
        import tomllib
        contract = workspace_digest(prepare_workspace(root, tmp_path / 'contract',
                                   workspace_policy(tomllib.loads(manifest))))
    result = evaluate(descriptor, case_artifact=case_file, expected_case_id=entry['case_id'],
                      expected_content_sha256=entry['content_sha256'],
                      expected_environment_sha256=contract,
                      identity={'case_index': 0, 'attempt_id': 'first'}, **options)
    status = json.loads((result / 'run.json').read_text())
    assert status['status'] == 'succeeded', (result, (result / 'diagnostics.json').read_text())
    assert status['cleanup_status'] == 'succeeded'
    assert json.loads((result / 'judge/report.json').read_text())['status'] == 'pass'
    steps = result / 'inputs'
    assert json.loads((steps / '0001/result.json').read_text())['output'] == 'first step isolated'
    second = json.loads((steps / '0002/result.json').read_text())['output']
    assert second.startswith('future-')
    assert second not in (steps / '0001/result.json').read_text()
    assert json.loads((result / 'session.json').read_text())['invocations'] == 2
    print('Private storage acceptance:', result)

def test_missing_external_storage_support_fails_before_sdk_call(tmp_path):
    from agentbench.sdk.plugin.kuma.integration import storage_options
    called = []
    def old_sdk(*, repo_path):
        called.append(repo_path)
    with pytest.raises(RuntimeError, match='storage_path'):
        storage_options(old_sdk, tmp_path)
    assert called == []


def test_slots_exist_before_generation_and_attempts_stay_under_case(tmp_path):
    from agentbench.sdk.integration.lifecycle import allocate_run
    store = FileArtifactStore(tmp_path / 'suite')
    generation = allocate_run(tmp_path / 'legacy', store, 'agent', {}, (0, 1))
    assert generation.is_dir()
    assert store.case('agent', 1).directory.is_dir()
    attempt = allocate_run(tmp_path / 'legacy', store, 'agent',
                           {'case_index': 0, 'attempt_id': 'attempt-one'})
    assert attempt == store.case('agent', 0).directory / 'trajectory/attempt-one'


@pytest.mark.skipif(os.name == 'nt', reason='Controller transport runs in Linux')
def test_agent_response_cannot_follow_links_into_private_storage(tmp_path):
    from agentbench.sdk.integration.channel import collect_response
    source = tmp_path / 'response'
    source.mkdir()
    target = tmp_path / 'output'
    target.mkdir()
    private = tmp_path / 'private-case'
    private.write_text('future prompt')
    (source / 'result.json').symlink_to(private)
    with pytest.raises(OSError):
        collect_response(source, target)
    assert not (target / 'result.json').exists()


@pytest.mark.skipif(not hasattr(os, 'getuid') or getattr(os, 'getuid', lambda: -1)() != 0,
                    reason='Linux root-only ownership fixture')
def test_published_case_keeps_host_owner_for_future_attempts(tmp_path):
    import subprocess
    import sys
    from agentbench.runtime.docker.mount_permissions import _SCRIPT
    private = tmp_path / 'private'
    private.mkdir()
    (private / 'case.json').write_text('private')
    (private / 'case.json').chmod(0o600)
    shared = tmp_path / 'published'
    shared.mkdir()
    history = shared / 'old-case.json'
    history.write_text('immutable')
    os.chown(shared, 20002, 20002)
    os.chown(history, 20002, 20002)
    subprocess.run([sys.executable, '-I', '-S', '-c', _SCRIPT, 'agent',
                    '1', '20002', str(private), str(shared)], check=True)
    assert private.stat().st_uid == 10001
    assert (private / 'case.json').stat().st_uid == 10001
    assert shared.stat().st_uid == 20002
    assert shared.stat().st_gid == 10001
    assert shared.stat().st_mode & 0o777 == 0o770
    assert history.stat().st_uid == 20002 and history.read_text() == 'immutable'


def test_published_case_recovers_without_another_generation_request(tmp_path):
    from agentbench.sdk.common.artifacts import Artifacts
    from agentbench.sdk.plugin.kuma.generation import generate_collection
    from tests.test_case_preparation import generator
    calls = []
    create, options = generator(tmp_path / 'repo', calls=calls)
    publication = tmp_path / 'published'
    arguments = dict(count=1, options=options, repo=tmp_path / 'repo',
                     case_publications={'0': str(publication)})
    first = generate_collection(create, files=Artifacts(tmp_path / 'first'), **arguments)
    original = (publication / 'case.json').read_bytes()
    recovered = generate_collection(create, files=Artifacts(tmp_path / 'recovered'), **arguments)
    assert calls == [0]
    assert recovered['cases'] == first['cases']
    assert (publication / 'case.json').read_bytes() == original

    # A torn publication requires explicit repair; it must never silently bill
    # another Case or overwrite the original bytes.
    (publication / 'publication.json').unlink()
    with pytest.raises(ValueError, match='incomplete'):
        generate_collection(create, files=Artifacts(tmp_path / 'blocked'), **arguments)
    assert calls == [0]


def test_late_span_cannot_be_attributed_to_a_later_input(tmp_path):
    from opentelemetry.sdk.trace import TracerProvider
    from agentbench.runtime.agentcontainer.telemetry import WireExporter, WireSpanProcessor
    exporter = WireExporter()
    exporter.destination = tmp_path / 'first.jsonl'
    provider = TracerProvider()
    provider.add_span_processor(WireSpanProcessor(exporter))
    span = provider.get_tracer('test').start_span('unfinished old input')
    assert provider.force_flush() is False
    exporter.destination = tmp_path / 'second.jsonl'
    span.end()
    assert exporter.error == 'span_outside_transport_window'
    assert not (tmp_path / 'second.jsonl').exists()
    provider.shutdown()
