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
    snapshot.update(events=events, event_count=len(events), path=str(path),
                    total_case_count=sum(agent['case_count'] for agent in plan['agents']),
                    suite_error=snapshot.get('error'), parse_errors=[])
    return snapshot


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
