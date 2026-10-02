"""Read-only projection repairs for terminal SDK reports, preserving raw events."""
from copy import deepcopy
from pathlib import Path

from agentbench.harness.session.codec import benchmark_to_json, prepared_from_json
from agentbench.sdk.contracts import SDKResultReader
from agentbench.sdk.discovery import discover_sdks, load_sdk


def reconcile_reports(plan, events, snapshot):
    """Revalidate retained reports using the selected SDK's offline capability.

    Raw events and artifact files are never changed. Unreadable, mismatched or
    rejected evidence keeps its original result. No runner or credentials load.
    """
    candidates, replacements = [], {}
    for job in snapshot['jobs']:
        for case in job['cases']:
            for attempt in case['attempts']:
                result = attempt.get('result') or {}
                artifacts = result.get('artifacts') or {}
                sdk_error = artifacts.get('sdk_error') or {}
                if (artifacts.get('phase') == 'submission'
                        and (artifacts.get('completion') or {}).get('submission') == 'failed'
                        and sdk_error.get('type') and sdk_error.get('message')
                        and not artifacts.get('received_report')):
                    message = sdk_error['message']
                    native = artifacts.get('native_failure') or {}
                    if native.get('error'):
                        message += f"; Agent {native.get('error_type') or native.get('status')}: {native['error']}"
                    replacements[(job['agent_id'], case['case_index'], attempt['attempt_id'])] = {
                        **result, 'error': {'type': sdk_error['type'], 'code': sdk_error.get('code'),
                                          'message': message},
                        'artifacts': {**artifacts, **({'recovery': {**artifacts['recovery'],
                            'allow_replay': False,
                            'reason': 'SDK submission failed; inspect the original SDK and Agent errors before rerunning'}}
                            if (artifacts.get('recovery') or {}).get('action') == 'blocked' else {})},
                        'reconciled_from_artifacts': True}
                if (not result.get('benchmark') and artifacts.get('received_report')
                        and case.get('prepared_case') and attempt.get('judge_delivery_status') == 'received'):
                    candidates.append((job['agent_id'], case, attempt))
    if not candidates:
        return _project_events(events, replacements)
    name = (plan.get('configuration') or {}).get('sdk')
    try:
        reference = next((item for item in discover_sdks() if item.name == name), None)
        if reference is None:
            return _project_events(events, replacements)
        plugin = load_sdk(reference)
    except Exception:
        return _project_events(events, replacements)  # Optional dependencies cannot prevent reading a Suite.
    if not isinstance(plugin, SDKResultReader):
        return _project_events(events, replacements)
    for agent_id, case, attempt in candidates:
        result = attempt['result']
        artifacts = result['artifacts']
        value = attempt.get('artifact_directory') or artifacts.get('directory')
        if not isinstance(value, str):
            continue
        directory = Path(value)
        if not directory.is_absolute() or directory.is_symlink():
            continue
        try:
            from .view_api import RunViewAPI
            host = RunViewAPI(directory).read('run.json')
            identity = {'suite_id': plan['suite_id'], 'agent_id': agent_id,
                        'case_index': case['case_index'], 'case_id': case['case_id'],
                        'attempt_id': attempt['attempt_id'], 'run_id': directory.name}
            if any(host.get(key) != expected for key, expected in identity.items()):
                continue
            prepared = prepared_from_json(case['prepared_case'])
            benchmark = plugin.read_case_result(directory, prepared, agent_id=agent_id)
            # Only the native-failure/report conflation is repaired here.
            if benchmark.execution_status != 'failed' or benchmark.host_acceptance != 'accepted':
                continue
            failure = benchmark.failures[0]
            replacements[(agent_id, case['case_index'], attempt['attempt_id'])] = {
                **result, 'benchmark': benchmark_to_json(benchmark),
                'execution_status': 'failed', 'host_acceptance': 'accepted',
                'judge_delivery_status': 'received',
                'error': {'type': failure.error_type, 'message': failure.error_message},
                'artifacts': {**artifacts, 'host_acceptance': 'accepted',
                    'received_report': {**artifacts['received_report'], 'host_accepted': True},
                    'recovery': {'action': 'blocked', 'automatic': False, 'allow_replay': False,
                                 'reason': 'Judge completed; no Judge resubmission is needed'}},
                'reconciled_from_artifacts': True}
        except Exception:
            continue  # A saved verdict alone cannot override a validation failure.
    return _project_events(events, replacements)


def _project_events(events, replacements):
    if not replacements:
        return events
    projected = deepcopy(events)
    for event in projected:
        key = (event.get('agent_id'), event.get('case_index'), event.get('attempt_id'))
        if event.get('event') in {'case_completed', 'case_attempt_failed'} and key in replacements:
            event['case_result'] = replacements[key]
    return projected
