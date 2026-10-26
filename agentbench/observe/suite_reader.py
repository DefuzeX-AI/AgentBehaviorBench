"""Read a canonical Suite view without inventing recovery state for old logs."""

from pathlib import Path


def persisted_snapshot(result_log):
    """Return a coherent snapshot and raw events, or None for a legacy artifact."""
    path = Path(result_log)
    if path.name != 'events.json' or not (path.parent / 'plan.json').is_file():
        return None
    from agentbench.harness.session import read_suite, suite_snapshot
    plan, events = read_suite(path.parent)
    snapshot = suite_snapshot(plan, events)
    from .result_reconciliation import reconcile_reports
    projected = reconcile_reports(plan, events, snapshot)
    if projected is not events:
        snapshot = suite_snapshot(plan, projected)
    from .evaluation_source import evaluation_source
    snapshot['evaluation_source'] = evaluation_source(snapshot, plan)
    snapshot.update(events=events, event_count=len(events), path=str(path),
                    total_case_count=sum(agent['case_count'] for agent in plan['agents']),
                    suite_error=snapshot.get('error'), parse_errors=[])
    _restore_artifact_links(path, snapshot)
    from agentbench.harness.ground_truth.evaluator import read_evaluation
    try:
        snapshot['gt_evaluation'] = read_evaluation(path.parent, plan, events)
    except (OSError, ValueError):
        snapshot['gt_evaluation'] = {'status': 'invalid', 'provisional': True}
    return snapshot


def _restore_artifact_links(path, snapshot):
    """Link older native runs that recorded a directory but omitted its run ID.

    Use the same metadata/identity checks as artifact HTTP access. This enriches
    only the read projection; persisted events and execution outcomes stay intact.
    """
    from .view_api import SuiteRunCatalogAPI
    entries = SuiteRunCatalogAPI(path).entries(snapshot=snapshot)
    for job in snapshot['jobs']:
        for case in job['cases']:
            for attempt in case['attempts']:
                if attempt.get('artifact_run_id'):
                    continue
                artifacts = (attempt.get('result') or {}).get('artifacts') or {}
                directory = (attempt.get('artifact_directory') or
                             artifacts.get('artifact_directory') or artifacts.get('directory'))
                if not isinstance(directory, str):
                    continue
                candidate = Path(directory)
                entry = entries.get(candidate.name)
                if entry is None:
                    continue
                api, details = entry
                if (api.directory != candidate.resolve() or details.get('agent') != job['agent_id']
                    or details.get('case_index') != case['case_index']
                    or details.get('attempt_id') != attempt['attempt_id']):
                    continue
                attempt['artifact_run_id'] = candidate.name
                if case.get('active_attempt_id') == attempt['attempt_id']:
                    case['artifact_run_id'] = candidate.name


def attempt_references(snapshot):
    """Yield exact artifact references for every historical Attempt in this Suite."""
    for job in snapshot['jobs']:
        for case in job['cases']:
            for attempt in case['attempts']:
                result = attempt.get('result') or {}
                artifacts = result.get('artifacts') or {}
                identity = {**case, **attempt, 'suite_id': snapshot['suite_id'],
                            'agent_id': job['agent_id'], 'case_index': case['case_index']}
                directory = attempt.get('artifact_directory') or artifacts.get('artifact_directory') or artifacts.get('directory')
                if directory:
                    yield job['agent_id'], directory, identity
