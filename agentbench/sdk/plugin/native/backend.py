"""Fixed-input state machine owned by ABB, independent of Judge providers."""
from agentbench.sdk.integration.run import Run
from agentbench.sdk.integration.cases import snapshot


def validate_case(value):
    value = snapshot(value)
    inputs = value.get('inputs')
    if not isinstance(inputs, list) or not inputs:
        raise ValueError('ABB Case requires a non-empty inputs list')
    seen = set()
    for item in inputs:
        if not isinstance(item, dict) or 'payload' not in item:
            raise ValueError('Each ABB input requires input_id and payload')
        identity = item.get('input_id')
        if not isinstance(identity, str) or not identity.strip() or identity in seen:
            raise ValueError('ABB input IDs must be non-empty and unique')
        seen.add(identity)
    return value


class NativeRun(Run):
    def submit(self, output=None, *, status='completed', error=None):
        result = super().submit(output, status=status, error=error)
        if status != 'completed':
            self.state = 'completed'
        return result

    def get_input(self, *, full=False):
        if self.state == 'completed':
            return None
        return super().get_input(full=full)


def create_run(*, case=None, cases=(), case_index=0, evidence=None, **context):
    return NativeRun(validate_case(cases[case_index] if case is None else case), evidence=evidence)
