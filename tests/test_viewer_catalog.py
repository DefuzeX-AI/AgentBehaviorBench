"""Project Suite discovery, HTTP routing and shared CLI viewer links."""

import json
from urllib.request import urlopen

import pytest

from agentbench.cli import viewer, viewer_service
from agentbench.cli.viewer_catalog import ViewerSuiteCatalog
from agentbench.cli.sessions import control
from agentbench.harness.session import SuiteStore
from agentbench.harness.session.references import history_guard, register_suite_reference
from tests.test_suite_resume import make_agent, make_case, save_result
from tests.test_suite_viewer import serving, request


@pytest.fixture
def saved(tmp_path, monkeypatch):
    monkeypatch.setattr(viewer, 'project_root', lambda: tmp_path)
    web = tmp_path / 'web'
    web.mkdir()
    (web / 'index.html').write_text('<html><head></head><body>Viewer</body></html>')
    monkeypatch.setattr(viewer, 'WEB_ROOT', web)
    agent = make_agent(tmp_path, 1)
    def create(identifier, parent=None, origin=None):
        with SuiteStore.begin(parent or tmp_path / 'results/suites', identifier, [agent], origin_suite_id=origin) as store:
            case = store.retain_case(agent.agent_id, make_case(tmp_path / 'generation', 0))
            save_result(store, agent, case)
            store.append({'event': 'suite_completed'})
            return store.path
    return create


def test_catalog_discovers_new_nested_and_indexed_suites_with_missing_history(tmp_path, saved):
    first = saved('suite_first')
    catalog = ViewerSuiteCatalog(tmp_path, first)
    assert [s['suite_id'] for s in catalog.listing()['suites']] == ['suite_first']
    second = saved('suite_second', tmp_path / 'results/custom/suites', 'suite_first')
    external = saved('suite_external', tmp_path / 'external')
    with history_guard(tmp_path):
        register_suite_reference(external.parent, project_root=tmp_path)
    missing = saved('suite_missing', tmp_path / 'gone')
    with history_guard(tmp_path):
        register_suite_reference(missing.parent, project_root=tmp_path)
    missing.unlink()
    catalog.refresh(force=True)
    rows = catalog.listing()
    assert {s['suite_id'] for s in rows['suites']} == {'suite_first', 'suite_second', 'suite_external'}
    assert rows['warnings'] == ['Unavailable Suite: suite_missing']
    assert catalog.resolve('suite_second') == second
    assert next(s for s in rows['suites'] if s['suite_id'] == 'suite_second')['origin_suite_id'] == 'suite_first'


def test_root_and_deep_links_serve_all_suites_and_their_exact_snapshots(saved):
    first, second = saved('suite_first'), saved('suite_second', origin='suite_first')
    with serving(first) as base:
        for path, identifier in [('/', 'suite_first'), ('/suite/suite_second/', 'suite_second')]:
            with urlopen(base + path) as response:
                html = response.read().decode()
                assert 'abb-suites-api' in html
                assert f'/api/suites/{identifier}/result' in html
        assert {s['suite_id'] for s in request(base + '/api/suites')[1]['suites']} == {'suite_first', 'suite_second'}
        assert request(base + '/api/suites/suite_second/result')[1]['origin_suite_id'] == 'suite_first'
        assert request(base + '/api/suites/unknown/result')[0] == 404
        assert request(base + '/api/suites', origin='https://evil.example')[0] == 403


def test_artifacts_resolve_across_suites_but_unregistered_files_stay_unavailable(tmp_path, saved):
    first, second = saved('suite_first'), saved('suite_second')
    directory = tmp_path / 'observe/run_second'
    directory.mkdir(parents=True)
    (directory / 'run.json').write_text(json.dumps({'schema': 'abb.evaluate.run.v1', 'run_id': directory.name,
        'agent_id': 'test-agent', 'suite_id': 'suite_second', 'case_index': 0, 'attempt_id': 'initial-0'}))
    with SuiteStore.open(second.parent) as store:
        store.append({'event': 'progress', 'agent_id': 'test-agent', 'case_index': 0,
                      'attempt_id': 'initial-0', 'artifact_run_id': directory.name, 'artifact_directory': str(directory)})
    with serving(first) as base:
        status, metadata = request(base + '/api/observe/runs/run_second/metadata')
        assert status == 200 and metadata['run_id'] == 'run_second'
        assert request(base + '/api/observe/runs/unregistered/metadata')[0] == 404
        assert request(base + '/api/observe/runs/run_second/file?path=../../secret')[0] == 404


def test_control_token_is_scoped_to_selected_suite_and_catalog_closes_owned_workers(saved):
    first, second = saved('suite_first'), saved('suite_second')
    initial = control.register_control(first, {})
    try:
        with serving(first) as base:
            snapshot = request(base + '/api/suites/suite_second/result')[1]
            token = snapshot['capabilities']['control_token']
            assert token != initial.token
            assert request(base + '/api/suites/suite_first/commands', origin=base, token=token,
                           body={'command_id': 'wrong-suite', 'action': 'resume'})[0] == 403
            owned = control.get_control(second)
            assert owned is not None
        assert control.get_control(second) is None and not owned._thread.is_alive()
        assert control.get_control(first) is initial
    finally:
        initial.close()


def test_cli_attaches_to_running_project_viewer_without_closing_it(tmp_path, saved):
    first, second = saved('suite_first'), saved('suite_second')
    running = viewer.start_viewer_server(first, port=0)
    try:
        attached = viewer.start_viewer_server(second)
        assert attached.server is None
        assert attached.url == running.base_url + '/suite/suite_second/'
        attached.stop()
        assert request(running.base_url + '/api/suites/suite_second/result')[0] == 200
        assert viewer_service.find_viewer(tmp_path) == running.base_url
    finally:
        running.stop()
    assert viewer_service.find_viewer(tmp_path) is None


def test_duplicate_suite_ids_are_reported_without_silently_switching_files(tmp_path, saved):
    first = saved('suite_same')
    saved('suite_same', tmp_path / 'results/other/suites')
    catalog = ViewerSuiteCatalog(tmp_path, first)
    assert catalog.listing()['suites'] == []
    assert 'Ambiguous Suite ID: suite_same' in catalog.listing()['warnings']
    with pytest.raises(ValueError):
        catalog.resolve('suite_same')


def test_service_discovery_rejects_stale_and_foreign_records(tmp_path, saved):
    first = saved('suite_first')
    running = viewer.start_viewer_server(first, port=0)
    marker = tmp_path / 'cache/viewer-service.json'
    original = json.loads(marker.read_text())
    try:
        for changed in [[], {**original, 'instance_id': 'stale'},
                        {**original, 'project': 'another-project'},
                        {**original, 'base_url': 'https://example.com'}]:
            marker.write_text(json.dumps(changed))
            assert viewer_service.find_viewer(tmp_path) is None
        marker.write_text('[]')
        viewer_service.unpublish(tmp_path, original['instance_id'])
        assert marker.exists()
    finally:
        marker.write_text(json.dumps(original))
        running.stop()
