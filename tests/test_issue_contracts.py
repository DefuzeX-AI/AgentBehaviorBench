"""Public, offline regressions for the reported onboarding contracts."""
import asyncio
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import pytest
from agentbench.adapter.langgraph.adapter import LangGraphAdapter
from agentbench.adapter.langgraph.config import LangGraphAdapterConfig
from agentbench.harness import BenchmarkRunner
from tests.test_benchmark_runner import FakeSDKRun
from tests.test_registry import _write_registry
from agentbench.harness.registry import load_registry


def test_host_uses_one_loop_for_all_inputs(starter_agent):
    from agentbench.adapter import AdapterInvocation
    from agentbench.harness.runner.running_agent import RunningAgent
    loops = []
    class Adapter:
        is_loaded = True
        def invoke(self, *a, **kw):
            raise AssertionError('sync path used')
        async def ainvoke(self, value, **kw):
            loops.append(asyncio.get_running_loop())
            return AdapterInvocation(output=value, raw_output=value)
        async def aclose(self):
            assert asyncio.get_running_loop() is loops[0]
        def close(self):
            pass
    class Run(FakeSDKRun):
        def get_input(self, **kw):
            return self._input if len(loops) < 3 else None
    handle = RunningAgent(starter_agent, Adapter())
    runner = BenchmarkRunner(agent_runner=SimpleNamespace(start=lambda a: handle))
    result = runner.run(starter_agent, Run())
    assert len(result.steps) == 3 and len(set(loops)) == 1


@pytest.mark.parametrize('asynchronous', [False, True])
def test_context_is_forwarded_and_copied(tmp_path, asynchronous):
    config = LangGraphAdapterConfig(tmp_path, 'a', 'x.py:g', None, None, 'in_process', context={'items': []})
    adapter = LangGraphAdapter(config)
    class Graph:
        def invoke(self, value, config=None, *, context):
            assert context['items'] == []
            context['items'].append('changed')
            return value
    adapter._graph = Graph()
    for _ in range(2):
        result = asyncio.run(adapter.ainvoke('input')) if asynchronous else adapter.invoke('input')
        assert result.output == 'input'


def test_in_process_registration_needs_no_dockerfile(tmp_path):
    path = _write_registry(tmp_path)
    (tmp_path / 'resources/agents/test-agent/Dockerfile').unlink()
    assert load_registry(path).find('test-agent').agent_id == 'test-agent'


@pytest.mark.parametrize('command', ['run', 'certify'])
def test_external_registry_parser(command):
    from agentbench.cli.main import build_parser
    argv = [command] + (['any-agent'] if command == 'certify' else [])
    args = build_parser().parse_args(argv + ['--registry', '/tmp/external/resources/registry.toml'])
    assert Path(args.registry) == Path('/tmp/external/resources/registry.toml')


@pytest.mark.parametrize('value', ['../outside', '/tmp/outside'])
def test_docker_structure_rejects_escape_without_resolving_secrets(tmp_path, value):
    from agentbench.runtime.agentcontainer.config import docker_structure, ContainerConfigurationError
    manifest = {'runtime': {'type': 'docker', 'secret_env_keys': ['UNSET_TEST_SECRET']},
                'build': {'context': value, 'dockerfile': 'Dockerfile'}, 'launch': {'argv': ['python']}}
    with pytest.raises(ContainerConfigurationError, match='escapes'):
        docker_structure(tmp_path, manifest)


def test_context_relative_dockerfile_and_launch_validation(tmp_path):
    from agentbench.runtime.agentcontainer.config import docker_structure, ContainerConfigurationError
    (tmp_path / 'image').mkdir()
    (tmp_path / 'image/Customfile').write_text('FROM scratch')
    manifest = {'runtime': {'type': 'docker', 'secret_env_keys': ['UNSET_TEST_SECRET']},
                'build': {'context': 'image', 'dockerfile': 'Customfile'}, 'launch': {'argv': ['python']}}
    assert docker_structure(tmp_path, manifest)[1] == tmp_path / 'image/Customfile'
    manifest['launch']['argv'] = []
    with pytest.raises(ContainerConfigurationError, match='launch.argv'):
        docker_structure(tmp_path, manifest)


def test_existing_loop_requires_async_api(starter_agent):
    async def run():
        with pytest.raises(RuntimeError, match='await BenchmarkRunner.arun'):
            BenchmarkRunner().run(starter_agent, FakeSDKRun())
        assert (await BenchmarkRunner().arun(starter_agent, FakeSDKRun())).history_count == 1
    asyncio.run(run())


def test_viewer_missing_referenced_asset_fails_before_start(tmp_path, monkeypatch):
    from agentbench.cli import viewer
    (tmp_path / 'index.html').write_text('<script src="/assets/missing.js"></script>')
    monkeypatch.setattr(viewer, 'WEB_ROOT', tmp_path)
    with pytest.raises(viewer.ViewerUnavailable, match='npm ci'):
        viewer.require_viewer_assets()


@pytest.mark.parametrize('wrong_answer', [False, True])
def test_evaluate_retains_one_case_three_inputs(starter_agent, tmp_path, monkeypatch, wrong_answer):
    import json
    from agentbench.cli.main import cli
    from agentbench.cli.features import evaluate
    from agentbench.observe.view_api import SuiteRunCatalogAPI
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(evaluate, 'enabled_agents', lambda _: [{'agent_id': starter_agent.agent_id}])
    monkeypatch.setattr(evaluate, 'resolve_agent', lambda *_: replace(starter_agent, case_count=7))
    monkeypatch.setattr(evaluate, 'load_project_environment', lambda _: None)
    case = tmp_path / 'case.json'
    case.write_text(json.dumps({'inputs': [{'input_id': str(i), 'payload': f'hello-{i}',
        'expected_output': 'different' if wrong_answer else f'hello-{i}'} for i in range(3)]}))
    options = tmp_path / 'options.json'
    options.write_text(json.dumps({'case_file': str(case)}))
    assert cli(['evaluate', '1', '--cases', '1', '--sdk', 'python:examples.case_file_sdk', '--sdk-options', str(options),
                '--result-output', str(tmp_path / 'evaluation.json')]) == 0
    logs = list(tmp_path.glob('evaluation-*.json'))
    assert len(logs) == 1
    events = json.loads(logs[0].read_text())
    completed = next(event['item'] for event in events if event['event'] == 'agent_completed')
    assert completed['completed_case_count'] == 1
    assert completed['benchmarks'][0]['history_count'] == 3
    catalog = SuiteRunCatalogAPI(logs[0])
    entries = catalog.entries()
    assert len(entries) == 1
    api = next(iter(entries.values()))[0]
    assert len(api.evaluation()['inputs']) == 3
    assert api.evaluation()['public_result']['report']['status'] == ('issue' if wrong_answer else 'pass')


def test_result_artifacts_redact_secrets_without_mutating_input(tmp_path, monkeypatch):
    import json
    from agentbench.cli.result_export import start_result_log
    monkeypatch.setenv('FIXTURE_API_KEY', 'fixture-private-value')
    payload = {'message': 'fixture-private-value', 'authorization': 'Bearer credential'}
    log = start_result_log(tmp_path / 'result.json', suite_id='fixture', selected_agent_ids=('agent',))
    log.append_step_started('agent', 'input', payload)
    saved = json.loads(log.path.read_text())[-1]['payload']
    assert saved == {'message': '[REDACTED]', 'authorization': '[REDACTED]'}
    assert payload['message'] == 'fixture-private-value'


def test_external_registry_certify_then_run_from_other_cwd(starter_agent, repo_root, tmp_path):
    import json
    import os
    import shutil
    import subprocess
    import sys
    resources = tmp_path / 'workspace/resources'
    resources.mkdir(parents=True)
    shutil.copytree(starter_agent.path, resources.parent / 'unit')
    registry = resources / 'registry.toml'
    registry.write_text('schema_version = "defuzex-bench.registry.v1"\n[[agents]]\n'
        'agent_id = "test-echo"\npath = "unit"\nframework = "langgraph"\nstatus = "adapting"\n')
    case = tmp_path / 'case.json'
    case.write_text(json.dumps({'inputs': [{'input_id': 'one', 'payload': 'hello', 'expected_output': 'hello'}]}))
    options = tmp_path / 'options.json'
    options.write_text(json.dumps({'case_file': str(case)}))
    env_file = tmp_path / 'offline.env'
    env_file.write_text('ABB_OFFLINE_FIXTURE=1\n')
    bundled = repo_root / 'resources/registry.toml'
    original = bundled.read_bytes()
    env = {**os.environ, 'PYTHONPATH': str(repo_root)}
    common = ['--registry', str(registry), '--sdk', 'python:examples.case_file_sdk',
        '--sdk-options', str(options), '--env-file', str(env_file), '--output', str(tmp_path / 'result.json')]
    for command in (['certify', 'test-echo'], ['run', '--no-view']):
        process = subprocess.run([sys.executable, '-m', 'agentbench', *command, *common],
            input='y\n', capture_output=True, text=True, cwd=tmp_path, env=env, timeout=30)
        assert process.returncode == 0, process.stdout + process.stderr
    assert 'status = "ready"' in registry.read_text()
    assert bundled.read_bytes() == original
