"""Issue #66: the SDK repository mount leaves what the Agent image built at /opt/agent/agent visible."""
import asyncio
import json
from pathlib import Path

import pytest

from agentbench.sdk.plugin.kuma import worker
from agentbench.sdk.plugin.kuma.configuration import SDK_REPOSITORY
from agentbench.sdk.plugin.kuma.service import EvaluationPolicy
from tests.test_kuma_requirement import unit  # noqa: F401 - pytest fixture


def test_sdk_repository_is_mounted_beside_the_agent_tree_not_over_it(tmp_path):
    state = tmp_path / 'sdk-repo' / '.kuma'
    state.mkdir(parents=True)
    arguments = EvaluationPolicy(state).run_arguments()
    mounts = [arguments[index + 1] for index, value in enumerate(arguments) if value == '--mount']
    assert mounts == [
        f'type=bind,source={state.parent.resolve()},target={SDK_REPOSITORY},readonly',
        f'type=bind,source={state.resolve()},target={SDK_REPOSITORY}/.kuma',
    ]
    assert not any('/opt/agent/agent' in mount for mount in mounts)
    assert not SDK_REPOSITORY.startswith('/opt/agent/')


def test_container_entrypoint_passes_the_mounted_sdk_repository(tmp_path, monkeypatch):
    settings = tmp_path / 'evaluation.json'
    settings.write_text(json.dumps({'mode': 'generate', 'count': 1}))
    seen = {}

    async def execute(root, output, settings, sdk_repo=None):
        seen.update(root=root, sdk_repo=sdk_repo)
        return 0

    monkeypatch.setattr(worker, 'execute', execute)
    monkeypatch.setattr('sys.argv', ['worker', '--settings', str(settings), '--output', str(tmp_path)])
    assert worker.main() == 0
    assert seen == {'root': Path('/opt/agent'), 'sdk_repo': Path(SDK_REPOSITORY)}


def test_missing_sdk_at_startup_names_the_interpreter(tmp_path, monkeypatch):
    import sys
    from agentbench.sdk.plugin.kuma.diagnostics import collect_artifacts, failure_message
    settings = tmp_path / 'request/evaluation.json'
    settings.parent.mkdir()
    settings.write_text(json.dumps({'mode': 'generate', 'count': 1}))
    output = tmp_path / 'evaluation'
    output.mkdir()

    async def execute(root, output, settings, sdk_repo=None):
        raise ModuleNotFoundError("No module named 'kuma'", name='kuma')

    monkeypatch.setattr(worker, 'execute', execute)
    monkeypatch.setattr('sys.argv', ['worker', '--settings', str(settings), '--output', str(output)])
    assert worker.main() == 1
    error = json.loads((output / 'error.json').read_text())
    assert error['phase'] == 'startup' and error['type'] == 'ModuleNotFoundError'
    assert "No module named 'kuma'" in error['message'] and sys.executable in error['message']
    assert f'interpreter {sys.executable}' in failure_message(
        collect_artifacts(tmp_path, {'status': 'failed'}, environ={}))


def test_generation_uses_the_separate_repository_and_leaves_the_agent_tree_alone(
        unit, tmp_path, monkeypatch):  # noqa: F811 - pytest fixture
    import kuma

    create_run = kuma.create_run
    sdk_repo = tmp_path / 'abb-sdk-repo'
    sdk_repo.mkdir()
    observed = []

    def offline_create(**options):
        observed.append(options['repo_path'])
        options['allow_local'] = True
        return create_run(**options, case_provider=lambda context: {
            'case_id': 'mounted-case', 'input_type': 'text', 'inputs': [
                {'input_id': 'one', 'payload_type': 'text', 'payload': 'echo this'}]},
            judge_provider=lambda context: {'status': 'pass', 'issues': []})

    monkeypatch.setattr(kuma, 'create_run', offline_create)
    monkeypatch.setenv('KUMA_API_KEY', 'offline-not-sent')
    output = tmp_path / 'output'
    code = asyncio.run(worker.execute(unit, output, {'mode': 'generate', 'count': 1, 'max_steps': 1},
                                      sdk_repo=sdk_repo))
    error = output / 'error.json'
    assert code == 0, error.read_text() if error.exists() else 'generation failed'
    assert observed == [sdk_repo]
    assert (sdk_repo / '.kuma/abb-case-0001.json').is_file()
    assert not (unit / 'agent/.kuma').exists()
    assert json.loads((output / 'process.json').read_text())['repo'] == str(sdk_repo)


def test_in_process_callers_keep_the_agent_tree_as_repository(unit, tmp_path, monkeypatch):  # noqa: F811
    import kuma
    create_run = kuma.create_run
    observed = []

    def offline_create(**options):
        observed.append(options['repo_path'])
        options['allow_local'] = True
        return create_run(**options, case_provider=lambda context: {
            'case_id': 'in-place-case', 'input_type': 'text', 'inputs': [
                {'input_id': 'one', 'payload_type': 'text', 'payload': 'echo this'}]},
            judge_provider=lambda context: {'status': 'pass', 'issues': []})

    monkeypatch.setattr(kuma, 'create_run', offline_create)
    monkeypatch.setenv('KUMA_API_KEY', 'offline-not-sent')
    code = asyncio.run(worker.execute(unit, tmp_path / 'output', {'mode': 'generate', 'count': 1, 'max_steps': 1}))
    assert code == 0 and observed == [unit / 'agent']
    if not (unit / 'agent/.kuma/abb-case-0001.json').is_file():
        pytest.fail('in-place repository did not receive the saved Case')
