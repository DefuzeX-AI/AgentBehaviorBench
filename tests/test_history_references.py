"""Cleanup preserves every persisted Suite and its absolute Attempt references."""
import json
import subprocess
import sys
from types import SimpleNamespace

import pytest

from agentbench.cli.history import archive_history, history_targets, protected_history
from agentbench.harness.session import SuiteStore
from agentbench.harness.session.references import (
    collect_suite_references, history_guard, register_suite_reference,
)
from tests.test_suite_store import registration


def artifact(project, name):
    directory = project / 'results' / 'observe' / name
    directory.mkdir(parents=True)
    (directory / 'run.json').write_text('{"status":"failed"}')
    return directory


def saved_suite(project, directory, *attempts, terminal='suite_completed', index=False):
    agent = registration(project)
    with history_guard(project):
        with SuiteStore.begin(directory, 'suite_saved', [agent]) as store:
            for number, path in enumerate(attempts, 1):
                store.append({'event': 'progress', 'agent_id': agent.agent_id, 'case_index': 0,
                              'attempt_id': f'attempt-{number}', 'artifact_directory': str(path)})
            store.append({'event': terminal})
            if index:
                register_suite_reference(store.directory, project_root=project)
            return store.directory


def test_legacy_readonly_results_remain_recoverably_archivable(tmp_path):
    results = tmp_path / 'results'
    results.mkdir()
    (results / 'legacy.json').write_text('[{"event":"suite_completed"}]')
    artifact(tmp_path, 'legacy-run')
    targets = history_targets(tmp_path)
    assert {path.name for path in targets} == {'legacy.json', 'observe'}
    archive = archive_history(targets, tmp_path)
    assert not list(results.iterdir())
    assert (archive / 'legacy.json').is_file()
    assert (archive / 'observe/legacy-run/run.json').is_file()


@pytest.mark.parametrize('terminal', ['suite_completed', 'suite_failed'])
def test_canonical_suite_protects_all_attempts_and_parent_directories(tmp_path, terminal):
    failed = artifact(tmp_path, 'old-failed-attempt')
    current = artifact(tmp_path, 'current-attempt')
    suite = saved_suite(tmp_path, tmp_path / 'results/suites', failed, current, terminal=terminal)
    disposable = tmp_path / 'results/legacy.json'
    disposable.write_text('[]')
    references, = collect_suite_references(tmp_path)
    assert {suite, failed, current}.issubset(references.paths)
    assert set(protected_history(tmp_path)) == {tmp_path / 'results/suites', tmp_path / 'results/observe'}
    assert history_targets(tmp_path) == (disposable,)
    archive_history((disposable,), tmp_path)
    assert (failed / 'run.json').exists() and (current / 'run.json').exists()
    assert (suite / 'events.json').exists()


def test_external_indexed_suite_protects_default_attempt_directory(tmp_path):
    project = tmp_path / 'project'
    project.mkdir()
    run = artifact(project, 'run-one')
    suite = saved_suite(project, tmp_path / 'custom-output/suites', run, index=True)
    assert not suite.is_relative_to(project)
    assert history_targets(project) == ()
    assert protected_history(project) == {project / 'results/observe': ('suite_saved',)}
    entry, = (project / 'cache/suite-references').glob('*.json')
    assert json.loads(entry.read_text())['directory'] == str(suite)


def test_reference_created_after_preview_blocks_all_moves(tmp_path):
    run = artifact(tmp_path, 'was-unreferenced')
    targets = history_targets(tmp_path)
    saved_suite(tmp_path, tmp_path / 'custom/suites', run, index=True)
    with pytest.raises(ValueError, match='History changed after preview'):
        archive_history(targets, tmp_path)
    assert run.is_dir()
    assert not (tmp_path / 'cache/history-trash').exists()


@pytest.mark.parametrize('filename', ['plan.json', 'events.json'])
def test_malformed_durable_suite_fails_closed_before_any_move(tmp_path, filename):
    run = artifact(tmp_path, 'original')
    suite = saved_suite(tmp_path, tmp_path / 'results/suites', run)
    (suite / filename).write_text('{incomplete')
    with pytest.raises(ValueError, match='Cannot verify saved Suite'):
        history_targets(tmp_path)
    assert run.exists() and (suite / filename).exists()


def test_missing_indexed_suite_does_not_assume_its_artifacts_unreferenced(tmp_path):
    run = artifact(tmp_path, 'original')
    suite = saved_suite(tmp_path, tmp_path / 'custom/suites', run, index=True)
    (suite / 'events.json').unlink()
    with pytest.raises(ValueError, match='Cannot verify saved Suite'):
        archive_history((tmp_path / 'results/observe',), tmp_path)
    assert run.exists()


def test_malformed_reference_index_fails_closed(tmp_path):
    run = artifact(tmp_path, 'original')
    index = tmp_path / 'cache/suite-references'
    index.mkdir(parents=True)
    (index / 'broken.json').write_text('{}')
    with pytest.raises(ValueError, match='Invalid Suite reference index'):
        history_targets(tmp_path)
    assert run.exists()


def test_malformed_attempt_reference_metadata_fails_closed(tmp_path):
    run = artifact(tmp_path, 'original')
    agent = registration(tmp_path)
    with SuiteStore.begin(tmp_path / 'results/suites', 'suite_malformed', [agent]) as store:
        store.append({'event': 'case_completed', 'agent_id': agent.agent_id, 'case_index': 0,
                      'case_result': {'artifacts': []}})
    with pytest.raises(ValueError, match='Cannot verify artifact references'):
        history_targets(tmp_path)
    assert run.exists()


def test_creation_and_cleanup_guard_excludes_another_process(tmp_path):
    program = (
        'import sys\nfrom agentbench.harness.session.references import history_guard\n'
        'try:\n with history_guard(sys.argv[1]): print("acquired")\n'
        'except RuntimeError: print("locked")\n')
    with history_guard(tmp_path):
        output = subprocess.check_output([sys.executable, '-c', program, str(tmp_path)], text=True)
        assert output.strip() == 'locked'
    output = subprocess.check_output([sys.executable, '-c', program, str(tmp_path)], text=True)
    assert output.strip() == 'acquired'


def test_clean_dry_run_explains_protected_history_without_moving(tmp_path, monkeypatch, capsys):
    from agentbench.cli.features import clean
    run = artifact(tmp_path, 'original')
    suite = saved_suite(tmp_path, tmp_path / 'results/suites', run)
    disposable = tmp_path / 'results/legacy.json'
    disposable.write_text('[]')
    monkeypatch.setattr(clean, 'PROJECT_ROOT', tmp_path)
    assert clean.execute(SimpleNamespace(dry_run=True, yes=True)) == 0
    output = capsys.readouterr().out
    assert 'Retained for saved Suites' in output
    assert 'observe (1 saved Suite(s))' in output
    assert 'Scope: unreferenced top-level entries' in output
    assert disposable.exists() and run.exists() and suite.exists()
    assert not (tmp_path / 'cache/history-trash').exists()


def test_agent_output_cannot_manufacture_cleanup_protection(tmp_path):
    agent = registration(tmp_path)
    disposable = tmp_path / 'results/loose.json'
    disposable.parent.mkdir()
    disposable.write_text('[]')
    with SuiteStore.begin(tmp_path / 'results/suites', 'suite_output', [agent]) as store:
        store.append({'event': 'case_completed', 'agent_id': agent.agent_id, 'case_index': 0,
                      'case_result': {'benchmark': {'steps': [{'output': {
                          'artifact_directory': str(disposable)}}]}}})
    assert history_targets(tmp_path) == (disposable,)
