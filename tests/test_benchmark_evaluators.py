"""SDK-scoped volume and reviewed discovery never mix independent evaluators."""

from copy import deepcopy
from dataclasses import replace
import json

from agentbench.cli.viewer_catalog import ViewerSuiteCatalog
from agentbench.cli.viewer_overview import benchmark_evaluators
from agentbench.harness.ground_truth import ASSESSMENTS_SCHEMA, benchmark_ground_truth, digest_json
from agentbench.harness.session import SuiteStore
from agentbench.observe.evaluation_source import evaluation_source
from tests.test_ground_truth import ground_truth_fixture, write_json
from tests.test_suite_resume import make_agent, make_case, save_result


def record_source(record, sdk):
    record['snapshot']['state'] = 'completed'
    record['plan']['configuration'] = {'sdk': sdk}
    record['snapshot']['evaluation_source'] = evaluation_source(record['snapshot'], record['plan'])
    return record


def test_catalog_groups_each_suite_and_shared_agent_by_saved_sdk(tmp_path):
    agent = make_agent(tmp_path, 1)
    for suite_id, sdk, counts in [
        ('suite_kuma_first', 'kuma', {'shared': 2, 'kuma-only': 1}),
        ('suite_kuma_second', 'kuma', {'shared': 1}),
        ('suite_local', 'local', {'shared': 1}),
        ('suite_custom', 'custom-evaluator', {'shared': 3}),
    ]:
        registrations = [replace(agent, agent_id=name, case_count=count) for name, count in counts.items()]
        with SuiteStore.begin(tmp_path / 'results/suites', suite_id, registrations,
                              configuration={'sdk': sdk}) as store:
            for registration in registrations:
                for index in range(registration.case_count):
                    case = store.retain_case(registration.agent_id, make_case(tmp_path / 'generation', index))
                    save_result(store, registration, case)
            store.append({'event': 'suite_completed'})
    overview = ViewerSuiteCatalog(tmp_path).overview()
    assert overview['totals'] == {'suite_count': 4, 'agent_count': 2, 'case_count': 8, 'completed_case_count': 8}
    evaluators = {row['id']: row for row in overview['evaluators']}
    assert list(evaluators) == ['custom-evaluator', 'kuma', 'local']
    assert evaluators['kuma']['totals'] == {
        'suite_count': 2, 'agent_count': 2, 'case_count': 4, 'completed_case_count': 4}
    assert evaluators['local']['totals'] == {
        'suite_count': 1, 'agent_count': 1, 'case_count': 1, 'completed_case_count': 1}
    assert evaluators['kuma']['agents'][0]['agent_id'] == evaluators['local']['agents'][0]['agent_id'] == 'shared'
    assert evaluators['kuma']['agents'][0]['case_count'] == 3
    assert evaluators['local']['agents'][0]['case_count'] == 1
    suite_ids = [suite['suite_id'] for group in evaluators.values()
                 for agent in group['agents'] for suite in agent['suites']]
    assert set(suite_ids) == {'suite_kuma_first', 'suite_kuma_second', 'suite_local', 'suite_custom'}
    assert evaluators['custom-evaluator']['evaluation_source']['sdk'] == 'custom-evaluator'
    assert all(group['ground_truth']['status'] == 'not_configured' for group in evaluators.values())
    assert all(not group['warnings'] for group in evaluators.values())


def test_unknown_mixed_partial_and_custom_sdk_identities_are_distinct(tmp_path):
    records = []
    for index, (sdk, mode) in enumerate([
        ('kuma', 'local-container'), (None, None), ('__mixed__', None),
        (None, 'official-container'), ('kuma', None),
    ]):
        result = {'benchmark': {'provider_mode': mode}} if mode else None
        snapshot = {'suite_id': f'suite_{index}', 'state': 'completed',
                    'jobs': [{'agent_id': 'shared', 'cases': [{'result': result}, {}]}]}
        plan = {'configuration': {'sdk': sdk}}
        snapshot['evaluation_source'] = evaluation_source(snapshot, plan)
        records.append({'snapshot': snapshot, 'plan': plan, 'directory': tmp_path / f'suite_{index}'})
    evaluators = {row['id']: row for row in benchmark_evaluators(tmp_path, records)}
    assert set(evaluators) == {'__mixed__', 'kuma', '@mixed', '@not_recorded', '@partial'}
    assert sum(row['totals']['suite_count'] for row in evaluators.values()) == 5
    assert sum(row['totals']['case_count'] for row in evaluators.values()) == 10
    assert evaluators['@mixed']['evaluation_source']['sdks'] == ['kuma', 'local']
    assert evaluators['@mixed']['totals']['suite_count'] == 1
    assert evaluators['@not_recorded']['evaluation_source']['status'] == 'not_recorded'
    assert evaluators['@partial']['evaluation_source']['status'] == 'partial'
    assert evaluators['@partial']['evaluation_source']['sdks'] == ['kuma']
    assert evaluators['@partial']['evaluation_source']['configured_sdk'] is None
    assert evaluators['kuma']['totals']['suite_count'] == 1
    assert evaluators['__mixed__']['evaluation_source']['sdk'] == '__mixed__'


def test_discovery_is_recomputed_per_sdk_and_excludes_agents_that_sdk_never_ran(tmp_path):
    kuma = ground_truth_fixture(tmp_path, 'alpha', 'suite_kuma')
    kuma.save_reviews(kuma.review)
    record_source(kuma.record, 'kuma')
    # The same Agent and defect can be discovered by one SDK and missed by another.
    local = deepcopy(kuma.record)
    directory = tmp_path / 'results/suites/suite_local'
    local['directory'] = directory
    local['plan']['suite_id'] = local['snapshot']['suite_id'] = 'suite_local'
    artifact = directory / 'cases/alpha/0/case.json'
    write_json(artifact, json.loads(kuma.artifact.read_text()))
    local['snapshot']['jobs'][0]['cases'][0]['prepared_case']['artifact_path'] = str(artifact)
    record_source(local, 'local')
    local_assessment = directory / 'ground_truth/assessments.json'
    missed = {**kuma.review, 'judge_detected': False}
    write_json(local_assessment, {'schema': ASSESSMENTS_SCHEMA, 'suite_id': 'suite_local', 'assessments': [missed]})
    beta = ground_truth_fixture(tmp_path, 'beta', 'suite_beta')
    beta.save_reviews(beta.review)
    record_source(beta.record, 'kuma')
    # A registered Agent with no saved Suite must not inflate an SDK denominator.
    ground_truth_fixture(tmp_path, 'not-run', 'suite_unused')
    records = [kuma.record, local, beta.record]

    def groups():
        return {row['id']: row for row in benchmark_evaluators(tmp_path, records)}

    result = groups()
    assert result['kuma']['ground_truth']['defect_count'] == 2
    assert result['kuma']['ground_truth']['discovered_defect_count'] == 2
    assert result['kuma']['ground_truth']['discovery_rate'] == 1
    assert result['local']['ground_truth']['defect_count'] == 1
    assert result['local']['ground_truth']['discovered_defect_count'] == 0
    assert result['local']['ground_truth']['discovery_rate'] == 0
    assert result['local']['totals']['agent_count'] == 1
    assert [agent['agent_id'] for agent in result['local']['agents']] == ['alpha']
    assert all(not group['ground_truth']['warnings'] for group in result.values())
    # Reviews refresh without Suite events or a catalog cache invalidation.
    write_json(local_assessment, {'schema': ASSESSMENTS_SCHEMA, 'suite_id': 'suite_local',
                                 'assessments': [kuma.review]})
    assert groups()['local']['ground_truth']['discovered_defect_count'] == 1
    kuma.save_reviews({**kuma.review, 'judge_detected': False})
    result = groups()
    assert result['kuma']['ground_truth']['discovered_defect_count'] == 1
    assert result['local']['ground_truth']['discovered_defect_count'] == 1
    # The preexisting all-SDK API retains its registered-but-unrun Agent behavior.
    assert benchmark_ground_truth(tmp_path, records, ['alpha', 'beta'])['totals']['defect_count'] == 3


def test_empty_catalog_has_no_evaluators_and_scoped_ground_truth_is_empty(tmp_path):
    ground_truth_fixture(tmp_path)
    overview = ViewerSuiteCatalog(tmp_path).overview()
    assert overview['evaluators'] == []
    assert overview['ground_truth']['defect_count'] == 1
    scoped = benchmark_ground_truth(tmp_path, [], [], include_unrun_agents=False)
    assert scoped['agents'] == {}
    assert scoped['totals']['defect_count'] == 0


def test_partial_suite_discovery_is_not_credited_to_its_only_known_sdk(tmp_path):
    partial = ground_truth_fixture(tmp_path, 'alpha', 'suite_partial')
    partial.result['benchmark']['provider_mode'] = 'official-container'
    partial.record['snapshot']['jobs'][0]['cases'].append({'case_index': 1})
    partial.save_reviews({**partial.review, 'result_sha256': digest_json(partial.result)})
    record_source(partial.record, None)
    assert partial.record['snapshot']['evaluation_source']['status'] == 'partial'
    kuma = deepcopy(partial.record)
    kuma['snapshot']['suite_id'] = kuma['plan']['suite_id'] = 'suite_kuma'
    kuma['directory'] = tmp_path / 'results/suites/suite_kuma'
    record_source(kuma, 'kuma')
    groups = {row['id']: row for row in benchmark_evaluators(tmp_path, [partial.record, kuma])}
    assert groups['@partial']['ground_truth']['discovered_defect_count'] == 1
    assert groups['kuma']['ground_truth']['discovered_defect_count'] == 0
    assert groups['kuma']['ground_truth']['discovery_rate'] is None
