"""Benchmark volume counts saved Case slots across the valid Suite catalog."""

from dataclasses import replace
import json
from urllib.request import urlopen

import pytest

from agentbench.cli import viewer
from agentbench.cli.viewer_catalog import ViewerSuiteCatalog
from agentbench.harness.session import SuiteStore
from agentbench.harness.session.admission import admit_reuse_request
from agentbench.harness.session.references import history_guard, register_suite_reference
from tests.test_suite_resume import make_agent, make_case, save_result
from tests.test_suite_viewer import request, serving


@pytest.fixture
def saved(tmp_path, monkeypatch):
    monkeypatch.setattr(viewer, 'project_root', lambda: tmp_path)
    web = tmp_path / 'web'
    web.mkdir()
    (web / 'index.html').write_text('<html><head></head><body>Viewer</body></html>')
    monkeypatch.setattr(viewer, 'WEB_ROOT', web)
    agent = make_agent(tmp_path, 10)

    def create(identifier, counts, *, completed=False, origin=None, parent=None):
        agents = [replace(agent, agent_id=name, case_count=count) for name, count in counts.items()]
        with SuiteStore.begin(parent or tmp_path / 'results/suites', identifier, agents, origin_suite_id=origin) as store:
            if completed:
                for registration in agents:
                    for index in range(registration.case_count):
                        case = store.retain_case(registration.agent_id, make_case(tmp_path / 'generation', index))
                        save_result(store, registration, case, verdict='issue' if index == 0 else 'pass')
                store.append({'event': 'suite_completed'})
            return store.path
    return create


def test_agent_volume_sums_each_suites_case_counts_and_keeps_execution_separate(tmp_path, saved):
    first = saved('suite_first', {'alpha': 10}, completed=True)
    saved('suite_second', {'alpha': 10}, completed=True)
    waiting = saved('suite_waiting', {'beta': 3})
    with SuiteStore.open(waiting.parent) as store:
        store.append({'event': 'case_generation_failed', 'agent_id': 'beta', 'case_index': 0})
    overview = ViewerSuiteCatalog(tmp_path, first).overview()
    assert overview['totals'] == {'suite_count': 3, 'agent_count': 2, 'case_count': 23, 'completed_case_count': 20}
    alpha, beta = overview['agents']
    assert (alpha['agent_id'], alpha['suite_count'], alpha['case_count'], alpha['completed_case_count']) == ('alpha', 2, 20, 20)
    assert [suite['case_count'] for suite in alpha['suites']] == [10, 10]
    assert beta['completed_case_count'] == 0
    assert 'events' not in json.dumps(overview)


def test_retry_updates_completion_without_counting_the_case_again(tmp_path, saved):
    path = saved('suite_retry', {'alpha': 1}, completed=True)
    catalog = ViewerSuiteCatalog(tmp_path, path)
    assert catalog.overview()['totals']['completed_case_count'] == 1
    identity = {'agent_id': 'alpha', 'case_index': 0, 'attempt_id': 'retry-2', 'attempt_number': 2}
    with SuiteStore.open(path.parent) as store:
        store.append({'event': 'case_attempt_started', **identity})
        catalog.refresh(force=True)
        assert catalog.overview()['totals'] == {'suite_count': 1, 'agent_count': 1, 'case_count': 1, 'completed_case_count': 0}
        store.append({'event': 'case_completed', **identity, 'case_result': {'status': 'succeeded', 'case_index': 0}})
    catalog.refresh(force=True)
    assert catalog.overview()['totals']['case_count'] == catalog.overview()['totals']['completed_case_count'] == 1


def test_live_reuse_admission_adds_slots_even_when_case_ids_repeat(tmp_path, saved):
    source = saved('suite_source', {'alpha': 1}, completed=True)
    child = saved('suite_reuse', {'alpha': 1}, origin='suite_source')
    catalog = ViewerSuiteCatalog(tmp_path, source)
    assert catalog.overview()['totals']['case_count'] == 2
    with SuiteStore.open(source.parent) as original, SuiteStore.open(child.parent) as store:
        prepared = original.snapshot()['jobs'][0]['cases'][0]['prepared_case']
        entry = {'agent_id': 'alpha', 'prepared_case': prepared,
                 'origin': {'suite_id': 'suite_source', 'agent_id': 'alpha', 'case_index': 0}}
        for request_id in ('reuse-1', 'reuse-2'):
            admit_reuse_request(store, {'request_id': request_id, 'agents': store.plan['agents'], 'cases': [entry]})
    catalog.refresh(force=True)
    overview = catalog.overview()
    assert overview['totals'] == {'suite_count': 2, 'agent_count': 1, 'case_count': 4, 'completed_case_count': 1}
    assert sorted(suite['case_count'] for suite in overview['agents'][0]['suites']) == [1, 3]


def test_catalog_deduplicates_references_and_excludes_unavailable_or_ambiguous_suites(tmp_path, saved):
    first = saved('suite_first', {'alpha': 2, 'beta': 1}, completed=True)
    external = saved('suite_external', {'alpha': 5}, parent=tmp_path / 'external')
    with history_guard(tmp_path):
        register_suite_reference(first.parent, project_root=tmp_path)
        register_suite_reference(external.parent, project_root=tmp_path)
    catalog = ViewerSuiteCatalog(tmp_path, first)
    assert catalog.overview()['totals'] == {'suite_count': 2, 'agent_count': 2, 'case_count': 8, 'completed_case_count': 3}
    first.write_text('{broken')
    catalog.refresh(force=True)
    overview = catalog.overview()
    assert overview['totals']['case_count'] == 5
    assert overview['warnings'] == ['Unavailable Suite: suite_first']
    saved('suite_external', {'alpha': 100}, parent=tmp_path / 'results/duplicate')
    catalog.refresh(force=True)
    overview = catalog.overview()
    assert overview['totals'] == {'suite_count': 0, 'agent_count': 0, 'case_count': 0, 'completed_case_count': 0}
    assert 'Ambiguous Suite ID: suite_external' in overview['warnings']


def test_overview_api_is_read_only_same_origin_and_keeps_suite_deep_links(saved):
    first = saved('suite_first', {'alpha': 10}, completed=True)
    saved('suite_second', {'alpha': 10, 'beta': 5})
    with serving(first) as base:
        status, overview = request(base + '/api/benchmark/overview')
        assert status == 200 and overview['schema'] == 'abb.benchmark.overview.v1'
        assert overview['totals'] == {'suite_count': 2, 'agent_count': 2, 'case_count': 25, 'completed_case_count': 10}
        assert overview['ground_truth']['status'] == 'not_configured'
        assert overview['ground_truth']['discovery_rate'] is None
        assert overview['ground_truth']['discovered_defect_count'] == 0
        assert all(agent['ground_truth']['status'] == 'not_configured' for agent in overview['agents'])
        assert request(base + '/api/benchmark/overview', origin='https://evil.example')[0] == 403
        for route in ['/', '/suite/suite_second/']:
            with urlopen(base + route) as response:
                assert 'abb-suites-api' in response.read().decode()
        assert request(base + '/api/suites/suite_second/result')[1]['suite_id'] == 'suite_second'


def test_empty_catalog_and_legacy_results_use_the_same_completion_definition(tmp_path):
    assert ViewerSuiteCatalog(tmp_path).overview()['totals'] == {
        'suite_count': 0, 'agent_count': 0, 'case_count': 0, 'completed_case_count': 0}
    path = tmp_path / 'legacy.json'
    path.write_text(json.dumps([
        {'event': 'run_started', 'suite_id': 'suite_legacy', 'selected_agent_ids': ['alpha'], 'selected_case_counts': {'alpha': 3}},
        {'event': 'agent_completed', 'agent_id': 'alpha', 'item': {'agent_id': 'alpha', 'case_results': [
            {'case_index': 0, 'status': 'failed', 'benchmark': {'report': {'status': 'issue'}}},
            {'case_index': 1, 'status': 'failed', 'error': {'type': 'TimeoutError'}},
        ]}},
    ]))
    overview = ViewerSuiteCatalog(tmp_path, path).overview()
    assert overview['totals'] == {'suite_count': 1, 'agent_count': 1, 'case_count': 3, 'completed_case_count': 1}


def test_ground_truth_updates_without_new_suite_events(tmp_path, saved):
    path = saved('suite_ground_truth', {'alpha': 1}, completed=True)
    resources = tmp_path / 'resources'
    resources.mkdir()
    (resources / 'registry.toml').write_text('[[agents]]\nagent_id = "alpha"\npath = "agent-source"\n')
    (tmp_path / 'agent-source/agent.toml').write_text('agent_id = "alpha"\n')
    catalog = ViewerSuiteCatalog(tmp_path, path)
    assert catalog.overview()['agents'][0]['ground_truth']['status'] == 'not_configured'
    reference = tmp_path / 'agent-source/ground_truth'
    reference.mkdir()
    manifest = reference / 'manifest.json'
    manifest.write_text(json.dumps({'schema': 'abb.agent.ground_truth.v1', 'agent_id': 'alpha', 'defects': []}))
    # No refresh(force=True): these files change independently of the cached events.
    overview = catalog.overview()
    assert overview['agents'][0]['ground_truth']['status'] == 'empty'
    assert overview['ground_truth']['discovery_rate'] is None
    manifest.write_text('{broken')
    overview = catalog.overview()
    assert overview['agents'][0]['ground_truth']['status'] == 'invalid'
    assert overview['ground_truth']['warnings']
    assert overview['totals']['completed_case_count'] == 1
