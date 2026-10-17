"""Suite artifact discovery reads each directory once without caching identities."""

from collections import Counter
import json
from pathlib import Path

import pytest

from agentbench.observe.view_api import SuiteRunCatalogAPI


def artifact(tmp_path, run_id='run_one', **changes):
    directory = tmp_path / 'runs' / run_id
    directory.mkdir(parents=True, exist_ok=True)
    metadata = {'schema': 'abb.evaluate.run.v1', 'run_id': run_id, 'agent_id': 'alpha',
                'suite_id': 'suite_one', 'case_index': 0, 'attempt_id': 'attempt-1',
                'status': 'running', **changes}
    (directory / 'run.json').write_text(json.dumps(metadata), encoding='utf-8')
    return directory


def progress(directory, **identity):
    return {'event': 'progress', 'agent_id': 'alpha', 'artifact_directory': str(directory),
            'artifact_run_id': directory.name, 'suite_id': 'suite_one', 'case_index': 0,
            'attempt_id': 'attempt-1', **identity}


def save_events(path, references):
    events = [{'event': 'run_started', 'suite_id': 'suite_one',
               'selected_agent_ids': ['alpha', 'beta']}, *references]
    path.write_text(json.dumps(events), encoding='utf-8')


@pytest.mark.parametrize('run_count', [1, 3])
def test_run_listing_metadata_io_scales_with_unique_directories(tmp_path, monkeypatch, run_count):
    directories = [artifact(tmp_path, f'run_{index}') for index in range(run_count)]
    path = tmp_path / 'events.json'
    catalog = SuiteRunCatalogAPI(path)
    reads, stats = Counter(), Counter()
    original_read, original_stat = Path.read_text, Path.stat

    def read_text(path, *args, **kwargs):
        if path.name == 'run.json':
            reads[Path(path)] += 1
        return original_read(path, *args, **kwargs)

    def stat(path, *args, **kwargs):
        if path.name == 'run.json':
            stats[Path(path)] += 1
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'read_text', read_text)
    monkeypatch.setattr(Path, 'stat', stat)
    references = [progress(directory) for directory in directories]
    save_events(path, references)
    expected_runs = catalog.route('/api/observe/runs', {})['runs']
    expected_reads, expected_stats = reads.copy(), stats.copy()
    assert expected_reads == Counter({directory / 'run.json': 1 for directory in directories})

    reads.clear()
    stats.clear()
    save_events(path, references * 1000)
    assert catalog.route('/api/observe/runs', {})['runs'] == expected_runs
    assert reads == expected_reads
    assert stats == expected_stats


@pytest.mark.parametrize('conflict', [
    {'agent_id': 'beta'}, {'suite_id': 'foreign-suite'}, {'case_index': 1},
    {'attempt_id': 'foreign-attempt'}, {'artifact_run_id': 'foreign-run'},
])
def test_each_reference_is_validated_and_valid_identities_are_merged(tmp_path, conflict):
    directory = artifact(tmp_path)
    path = tmp_path / 'events.json'
    invalid = progress(directory, **conflict, job_id='invalid-job', case_id='invalid-case')
    save_events(path, [invalid, progress(directory, job_id='job-one'),
                       progress(directory, case_id='case-one'), invalid])

    runs = SuiteRunCatalogAPI(path).route('/api/observe/runs', {})['runs']

    assert len(runs) == 1
    assert runs[0]['agent'] == 'alpha'
    assert runs[0]['job_id'] == 'job-one'
    assert runs[0]['case_id'] == 'case-one'
    assert runs[0]['attempt_id'] == 'attempt-1'


def test_each_listing_observes_metadata_creation_updates_and_removal(tmp_path):
    directory = tmp_path / 'runs' / 'run_one'
    path = tmp_path / 'events.json'
    save_events(path, [progress(directory)] * 5)
    catalog = SuiteRunCatalogAPI(path)
    assert catalog.route('/api/observe/runs', {})['runs'] == []

    artifact(tmp_path)
    assert catalog.route('/api/observe/runs', {})['runs'][0]['status'] == 'running'
    artifact(tmp_path, status='succeeded')
    assert catalog.route('/api/observe/runs', {})['runs'][0]['status'] == 'succeeded'

    (directory / 'run.json').unlink()
    assert catalog.route('/api/observe/runs', {})['runs'] == []


def test_metadata_cache_uses_directory_not_run_id(tmp_path):
    foreign = artifact(tmp_path / 'foreign', agent_id='beta')
    registered = artifact(tmp_path / 'registered')
    path = tmp_path / 'events.json'
    save_events(path, [progress(foreign), progress(registered)])

    entries = SuiteRunCatalogAPI(path).entries()

    assert list(entries) == ['run_one']
    assert Path(entries['run_one'][0].directory) == registered


def test_project_catalog_refresh_sees_metadata_changes_without_new_suite_events(tmp_path):
    from agentbench.cli.viewer_catalog import ViewerSuiteCatalog
    from agentbench.harness.registry import AgentRegistration
    from agentbench.harness.session import SuiteStore

    source = tmp_path / 'agent'
    source.mkdir()
    agent = AgentRegistration('alpha', source, True, 'ready', 'test', 'test', 1)
    directory = tmp_path / 'runs' / 'run_one'
    with SuiteStore.begin(tmp_path / 'results/suites', 'suite_one', [agent]) as store:
        store.append(progress(directory))
        path = store.path
    original_events = path.read_bytes()
    catalog = ViewerSuiteCatalog(tmp_path, path)
    catalog.refresh(force=True)
    with pytest.raises(ValueError, match='not registered'):
        catalog.artifact('run_one')

    artifact(tmp_path)
    catalog.refresh(force=True)
    assert catalog.artifact('run_one').read('run.json')['status'] == 'running'
    artifact(tmp_path, status='succeeded')
    catalog.refresh(force=True)
    assert catalog.artifact('run_one').read('run.json')['status'] == 'succeeded'

    artifact(tmp_path, agent_id='foreign-agent')
    catalog.refresh(force=True)
    with pytest.raises(ValueError, match='not registered'):
        catalog.artifact('run_one')
    assert path.read_bytes() == original_events
