"""Replacement SDKs work without importing KUMA or inheriting its settings."""

import json
import os
import shutil
import subprocess
import sys
from dataclasses import replace
from types import SimpleNamespace

import pytest

from tests.test_sdk_injection import forbid_defuzex


def test_contracts_import_without_harness_or_evaluators(repo_root):
    # A fresh interpreter prevents earlier imports from hiding dependency cycles.
    result = subprocess.run([sys.executable, '-c', '''
import sys
from agentbench.sdk import SDK, SDKRun, EvaluationRunner, EvaluationSDKPlugin
assert not any(name == "agentbench.harness" or name.startswith("agentbench.harness.")
               for name in sys.modules)
assert "agentbench.sdk.plugins" not in sys.modules
assert "kuma" not in sys.modules and "defuzex" not in sys.modules
from agentbench.harness import SDK as old_sdk
from agentbench.sdk.plugins import EvaluationSDKPlugin as old_plugin
assert old_sdk is SDK and old_plugin is EvaluationSDKPlugin
'''], cwd=repo_root, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('wrong_answer', [False, True])
def test_replacement_case_file_runs_real_agent(starter_agent, monkeypatch, tmp_path, wrong_answer):
    from agentbench.harness import SuiteRunner
    from examples import case_file_sdk

    forbid_defuzex(monkeypatch)
    case = tmp_path / 'case.json'
    case.write_text(json.dumps({'inputs': [
        {'input_id': 'one', 'payload': 'hello', 'expected_output': 'hello'},
        {'input_id': 'two', 'payload': '你好', 'expected_output': 'wrong' if wrong_answer else '你好'},
    ]}), encoding='utf-8')
    result = SuiteRunner(sdk=case_file_sdk, sdk_options={'case_file': case}).run(
        [replace(starter_agent, case_count=2)])
    assert result.passed is not wrong_answer
    assert result.items[0].completed_case_count == 2
    benchmarks = result.items[0].benchmarks
    assert len({run.run_id for run in benchmarks}) == 2
    assert all(run.history_count == 2 for run in benchmarks)
    assert all([step.invocation.output for step in run.steps] == ['hello', '你好'] for run in benchmarks)


def test_evaluate_cli_runs_replacement_without_kuma(starter_agent, repo_root, monkeypatch, capsys):
    from agentbench.cli.main import cli
    from agentbench.cli.features import evaluate

    forbid_defuzex(monkeypatch)
    monkeypatch.setattr(evaluate, 'enabled_agents', lambda _: [{'agent_id': starter_agent.agent_id}])
    monkeypatch.setattr(evaluate, 'resolve_agent', lambda *_: starter_agent)
    monkeypatch.setattr(evaluate, 'load_project_environment', lambda _: None)
    monkeypatch.chdir(repo_root)
    assert cli(['evaluate', '1', '--sdk', 'python:examples.case_file_sdk',
                '--sdk-options', 'examples/case_file_options.json']) == 0
    assert 'Judge: pass' in capsys.readouterr().out


def test_fresh_cli_process_with_kuma_unavailable(starter_agent, repo_root, tmp_path):
    # Exercise real registry parsing and CLI dispatch, with no cached SDK imports.
    shutil.copytree(starter_agent.path, tmp_path / 'agent')
    (tmp_path / 'agent/Dockerfile').write_text('FROM scratch\n')  # Unused by the local Agent.
    resources = tmp_path / 'resources'
    resources.mkdir()
    registry = resources / 'registry.toml'
    registry.write_text('schema_version = "defuzex-bench.registry.v1"\n'
                        '[[agents]]\nagent_id = "test-echo"\npath = "agent"\n'
                        'enabled = true\nstatus = "ready"\nframework = "langgraph"\n')
    env_file = tmp_path / 'offline.env'
    env_file.write_text('CASE_FILE_SDK_TEST=1\n')
    script = '''
import importlib.abc
import sys
class NoKuma(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"kuma", "defuzex"} or fullname in {
            "agentbench.sdk.kuma", "agentbench.sdk.defuzex",
        } or fullname.startswith("agentbench.sdk.kuma_runtime"):
            raise ImportError("Evaluator deliberately unavailable: " + fullname)
sys.meta_path.insert(0, NoKuma())
from agentbench.cli.main import cli
raise SystemExit(cli(sys.argv[1:]))
'''
    result = subprocess.run([
        sys.executable, '-c', script, 'evaluate', 'test-echo', '--registry', str(registry),
        '--env-file', str(env_file), '--sdk', 'python:examples.case_file_sdk',
        '--sdk-options', 'examples/case_file_options.json',
    ], cwd=repo_root, capture_output=True, text=True, timeout=30,
        env={k: v for k, v in os.environ.items() if k not in {'KUMA_API_KEY', 'DEFUZEX_API_KEY'}})
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'Judge: pass' in result.stdout


def test_evaluate_defaults_and_explicit_options_use_selected_factory(starter_agent, monkeypatch, tmp_path):
    from agentbench.cli.main import cli
    from agentbench.cli.features import evaluate
    from agentbench.sdk.kuma_runtime.benchmark import KumaContainerRunner

    monkeypatch.setattr(evaluate, 'enabled_agents', lambda _: [{'agent_id': starter_agent.agent_id}])
    monkeypatch.setattr(evaluate, 'resolve_agent', lambda *_: starter_agent)
    monkeypatch.setattr(evaluate, 'load_project_environment', lambda _: None)
    received = []

    def run(self, registration):
        assert registration is starter_agent
        received.append((self.sdk, self.output, self.timeout, self.environ['OPENROUTER_MODEL']))
        return SimpleNamespace(report=SimpleNamespace(status='issue'))

    monkeypatch.setattr(KumaContainerRunner, 'run', run)
    monkeypatch.setattr(KumaContainerRunner, 'validate_sdk', lambda *_: 'official-container')
    options = tmp_path / 'options.json'
    options.write_text(json.dumps({'output': str(tmp_path / 'from-json'), 'timeout': 11}))
    assert cli(['evaluate', '1', '--model', 'vendor/model', '--sdk-options', str(options),
                '--sdk-source', str(tmp_path / 'sdk'), '--output', str(tmp_path / 'override'),
                '--timeout', '12']) == 0
    assert received == [(tmp_path / 'sdk', tmp_path / 'override', 12, 'vendor/model')]


@pytest.mark.parametrize('preflight_fails', [False, True])
def test_evaluate_plugin_validates_before_execution(starter_agent, monkeypatch, preflight_fails):
    from agentbench.cli.main import cli
    from agentbench.cli.features import evaluate
    from agentbench.sdk import SDK_PLUGIN_API_VERSION

    forbid_defuzex(monkeypatch)
    calls = []

    class Runner:
        def validate_sdk(self, registration):
            assert registration is starter_agent
            calls.append('validate')
            if preflight_fails:
                raise ValueError('Replacement evaluator unavailable')
            return 'custom'

        def run(self, registration):
            assert registration is starter_agent
            calls.append('run')
            return SimpleNamespace(report=SimpleNamespace(status='pass'))

    class Plugin:
        name = 'replacement'
        api_version = SDK_PLUGIN_API_VERSION
        execution = 'local'

        def create_benchmark_runner(self, *, context, options):
            assert context.model == 'vendor/model'
            assert options == {}  # No implicit source path, timeout or output.
            return Runner()

    monkeypatch.setitem(sys.modules, 'replacement_sdk_fixture', SimpleNamespace(plugin=Plugin()))
    monkeypatch.setattr(evaluate, 'enabled_agents', lambda _: [{'agent_id': starter_agent.agent_id}])
    monkeypatch.setattr(evaluate, 'resolve_agent', lambda *_: starter_agent)
    monkeypatch.setattr(evaluate, 'load_project_environment', lambda _: None)
    assert cli(['evaluate', '1', '--sdk', 'python:replacement_sdk_fixture:plugin',
                '--model', 'vendor/model']) == (1 if preflight_fails else 0)
    assert calls == (['validate'] if preflight_fails else ['validate', 'run'])


def test_case_file_rejects_duplicate_ids_before_delivery(tmp_path):
    from examples.case_file_sdk import create_run

    path = tmp_path / 'case.json'
    row = {'input_id': 'same', 'payload': 'hello', 'expected_output': 'hello'}
    path.write_text(json.dumps({'inputs': [row, row]}))
    with pytest.raises(ValueError, match='unique'):
        create_run(repo_path=tmp_path, case_file=path)
