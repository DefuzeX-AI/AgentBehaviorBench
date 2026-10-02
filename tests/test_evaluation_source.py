"""Evaluator identity is saved provenance, independent of Agent/framework names."""

import json

import pytest

from agentbench.cli import viewer
from agentbench.cli.viewer_catalog import ViewerSuiteCatalog
from agentbench.harness.session import SuiteStore
from agentbench.observe.evaluation_source import evaluation_source
from tests.test_suite_resume import make_agent
from tests.test_suite_viewer import request, serving


def snapshot(*modes):
    return {'jobs': [{'agent_id': 'kuma-looking-agent', 'cases': [
        {'case_id': f'local-smoke-{index}', 'result': {'benchmark': {
            'adapter_name': 'container-sdk', 'provider_mode': mode}}}
        for index, mode in enumerate(modes)]}]}


@pytest.mark.parametrize('sdk', ['kuma', 'local', 'custom_judge'])
def test_saved_sdk_selection_identifies_queued_suites_without_running_plugins(sdk):
    source = evaluation_source(snapshot(None), {'configuration': {'sdk': sdk,
        'api_key': 'secret', 'provider_base_url': 'https://credential@example.com',
        'sdk_options': {'token': 'secret'}}})
    assert source['sdk'] == sdk and source['status'] == 'recorded'
    assert source['evidence'] == 'plan'
    assert source['provider_modes'] == []
    assert all(value not in json.dumps(source) for value in ('secret', 'credential', 'provider_base_url', 'sdk_options'))


def test_custom_sdk_name_is_not_overridden_by_its_shared_runtime_mode():
    source = evaluation_source(snapshot('official-container'), {'configuration': {'sdk': 'company.CustomJudge'}})
    assert source['sdk'] == 'company.CustomJudge'
    assert source['status'] == 'recorded'
    assert source['provider_modes'] == ['official-container']


def test_only_verified_legacy_modes_identify_sdk_not_framework_agent_case_or_unknown_mode():
    assert evaluation_source(snapshot('official-container'))['sdk'] == 'kuma'
    assert evaluation_source(snapshot('local-container'))['sdk'] == 'local'
    unknown = evaluation_source(snapshot('future-engine', None))
    assert unknown['status'] == 'not_recorded' and unknown['sdk'] is None
    assert unknown['sdks'] == [] and unknown['provider_modes'] == ['future-engine']
    assert evaluation_source(snapshot(), {'configuration': {'sdk': 'https://credential@host'}})['sdk'] is None


def test_mixed_attempt_history_and_configured_runtime_conflicts_stay_visible():
    value = snapshot('official-container')
    value['jobs'][0]['cases'][0]['attempts'] = [{'result': {'benchmark': {'provider_mode': 'local-container'}}}]
    source = evaluation_source(value)
    assert source['status'] == 'mixed' and source['sdk'] is None
    assert source['sdks'] == ['kuma', 'local']
    conflict = evaluation_source(snapshot('local-container'), {'configuration': {'sdk': 'kuma'}})
    assert conflict['status'] == 'mixed'
    assert conflict['configured_sdk'] == 'kuma'
    assert conflict['evidence'] == 'plan_and_results'


def test_partial_legacy_evidence_does_not_claim_all_cases_have_a_known_evaluator():
    source = evaluation_source(snapshot('official-container', None))
    assert source['status'] == 'partial' and source['sdk'] == 'kuma'
    assert source['evidence'] == 'results'
    assert evaluation_source({'jobs': []})['status'] == 'not_recorded'


def test_catalog_overview_and_result_api_share_safe_saved_source(tmp_path, monkeypatch):
    monkeypatch.setattr(viewer, 'project_root', lambda: tmp_path)
    web = tmp_path / 'web'
    web.mkdir()
    (web / 'index.html').write_text('<html><head></head><body>Viewer</body></html>')
    monkeypatch.setattr(viewer, 'WEB_ROOT', web)
    with SuiteStore.begin(tmp_path / 'results/suites', 'suite_source', [make_agent(tmp_path, 1)],
                          configuration={'sdk': 'local', 'provider_base_url': 'https://private.example'}) as store:
        path = store.path
    catalog = ViewerSuiteCatalog(tmp_path, path)
    source = catalog.listing()['suites'][0]['evaluation_source']
    assert source['sdk'] == 'local'
    assert catalog.overview()['agents'][0]['suites'][0]['evaluation_source'] == source
    assert viewer.parse_result_log(path)['evaluation_source'] == source
    with serving(path) as base:
        for url in ('/api/suites', '/api/suites/suite_source/result', '/api/benchmark/overview'):
            code, value = request(base + url)
            assert code == 200 and 'evaluation_source' in json.dumps(value)
            assert 'https://private.example' not in json.dumps(value)


def test_legacy_reader_uses_recorded_modes_without_a_plan(tmp_path):
    path = tmp_path / 'legacy.json'
    path.write_text(json.dumps([
        {'event': 'run_started', 'suite_id': 'suite_legacy', 'selected_agent_ids': ['agent']},
        {'event': 'agent_completed', 'agent_id': 'agent', 'item': {'agent_id': 'agent', 'case_results': [
            {'case_index': 0, 'status': 'succeeded', 'benchmark': {'adapter_name': 'container-sdk',
                'provider_mode': 'local-container', 'report': {'status': 'issue'}}}]}}
    ]))
    assert viewer.parse_result_log(path)['evaluation_source']['sdk'] == 'local'
