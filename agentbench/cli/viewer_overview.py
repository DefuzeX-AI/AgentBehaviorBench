"""Read-only benchmark totals from the Suites accepted by the viewer catalog."""

from urllib.parse import quote

from agentbench.harness.session.attempts import execution_status


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
