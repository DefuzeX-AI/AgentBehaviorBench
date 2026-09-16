"""Present the canonical Suite event store through the CLI result-log interface."""

from agentbench.cli.result_export import _summary_to_json, _suite_agent_to_json
from agentbench.harness.session import SuiteStore, case_to_json


class SuiteResultLog:
    """Immediate durable writes; all mutations stay on the Suite coordinator."""

    def __init__(self, store):
        self.store, self.path, self.suite_id = store, store.path, store.suite_id

    def append_event(self, event):
        if event.get('event') == 'case_prepared':
            # retain_case already checkpoints bytes and identity before dispatch.
            snapshot = self.store.snapshot()
            job = next((job for job in snapshot['jobs'] if job['agent_id'] == event['agent_id']), None)
            if job and job['cases'][event['case_index']]['prepared_case'] is not None:
                return
        self.store.append(event)

    def append_suite_complete(self, result):
        self.store.append({'event': 'suite_completed', 'summary': _summary_to_json(result)})

    def append_suite_error(self, exc):
        self.store.append({'event': 'suite_failed', 'error': {'type': type(exc).__name__, 'message': str(exc)}})

    def append_partial_results(self, items):
        snapshot = self.store.snapshot()
        known = {(job['agent_id'], case['case_index']): case['result']
                 for job in snapshot['jobs'] for case in job['cases']}
        for item in items:
            for case in item.case_results:
                value = case_to_json(case)
                if known.get((case.agent_id, case.case_index)) != value:
                    self.store.append({'event': 'case_completed', **value, 'case_result': value})
            self.store.append({'event': 'agent_completed', 'agent_id': item.agent_id,
                               'item': _suite_agent_to_json(item)})

    def flush(self):
        """Events are already flushed atomically before append returns."""

    flush_if_due = flush

    def close(self):
        self.store.close()
