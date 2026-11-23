"""Read-only benchmark totals from the Suites accepted by the viewer catalog."""

from urllib.parse import quote

from agentbench.harness.session.attempts import execution_status


def _evaluator_identity(source):
    if source.get('status') in {'mixed', 'partial'}:
        return f"@{source['status']}"
    return source.get('sdk') or '@not_recorded'


def _evaluator_source(sources):
    """Combine safe recorded identities without hiding partial legacy provenance."""
    sdks = sorted({sdk for source in sources for sdk in source.get('sdks', [])})
    configured = {source.get('configured_sdk') for source in sources}
    evidence = {source.get('evidence', 'none') for source in sources}
    has_plan = bool(evidence & {'plan', 'plan_and_results'})
    has_results = bool(evidence & {'results', 'plan_and_results'})
    status = ('mixed' if any(source.get('status') == 'mixed' for source in sources) else
              'not_recorded' if not sdks else
              'partial' if any(source.get('status') == 'partial' for source in sources) else 'recorded')
    return {'schema': 'abb.evaluation.source.v1', 'status': status,
            'sdk': sdks[0] if len(sdks) == 1 else None, 'sdks': sdks,
            'configured_sdk': next(iter(configured)) if len(configured) == 1 else None,
            'provider_modes': sorted({mode for source in sources for mode in source.get('provider_modes', [])}),
            'evidence': ('plan_and_results' if has_plan and has_results else
                         'plan' if has_plan else 'results' if has_results else 'none')}


def benchmark_evaluators(project_root, records):
    """Group each Suite once and reassess discovery only within its evaluator.

    Reserved identities start with ``@``, which is excluded from saved SDK names.
    Mixed and partial records stay separate: their findings cannot be attributed
    to one SDK for the entire Suite.
    """
    from agentbench.harness.ground_truth import benchmark_ground_truth

    groups = {}
    for record in records:
        source = record['snapshot'].get('evaluation_source') or {}
        groups.setdefault(_evaluator_identity(source), []).append(record)
    evaluators = []
    for identifier, group in sorted(groups.items(), key=lambda pair: (pair[0].startswith('@'), pair[0])):
        snapshots = [record['snapshot'] for record in group]
        agent_ids = {job['agent_id'] for snapshot in snapshots for job in snapshot['jobs']}
        ground_truth = benchmark_ground_truth(project_root, group, agent_ids, include_unrun_agents=False)
        overview = benchmark_overview(snapshots, ground_truth=ground_truth)
        evaluators.append({'id': identifier,
                           'evaluation_source': _evaluator_source([snapshot.get('evaluation_source') or {}
                                                                   for snapshot in snapshots]),
                           **overview})
    return evaluators


def benchmark_overview(snapshots, warnings=(), *, ground_truth=None):
    """Count Case slots, not Case IDs or Attempts; reuse contributes new slots."""
    agents = {}
    suite_count = 0
    for snapshot in snapshots:
        suite_count += 1
        identifier = snapshot['suite_id']
        for job in snapshot['jobs']:
            agent = agents.setdefault(job['agent_id'], {
                'agent_id': job['agent_id'], 'suite_count': 0, 'case_count': 0,
                'completed_case_count': 0, 'suites': [],
            })
            cases = job['cases']
            completed = sum((case.get('execution_status') or execution_status(case.get('result') or case))
                            == 'completed' for case in cases)
            agent['suite_count'] += 1
            agent['case_count'] += len(cases)
            agent['completed_case_count'] += completed
            agent['suites'].append({
                'suite_id': identifier, 'url': f'/suite/{quote(identifier, safe="")}/',
                'state': snapshot['state'], 'origin_suite_id': snapshot.get('origin_suite_id'),
                'evaluation_source': snapshot.get('evaluation_source'),
                'case_count': len(cases), 'completed_case_count': completed,
            })
    if ground_truth is not None:
        for identifier, metrics in ground_truth['agents'].items():
            agent = agents.setdefault(identifier, {'agent_id': identifier, 'suite_count': 0,
                'case_count': 0, 'completed_case_count': 0, 'suites': []})
            agent['ground_truth'] = metrics
    rows = sorted(agents.values(), key=lambda row: (-row['case_count'], row['agent_id']))
    overview = {
        'schema': 'abb.benchmark.overview.v1',
        'totals': {'suite_count': suite_count, 'agent_count': len(rows),
                   'case_count': sum(row['case_count'] for row in rows),
                   'completed_case_count': sum(row['completed_case_count'] for row in rows)},
        'agents': rows, 'warnings': list(warnings),
    }
    if ground_truth is not None:
        overview['ground_truth'] = {**ground_truth['totals'], 'warnings': ground_truth['warnings']}
    return overview
