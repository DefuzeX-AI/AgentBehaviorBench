import asyncio

import pytest

from agentbench.sdk.integration.dialogue import drive_run
from agentbench.sdk.integration.run import Input, Report, Run


class DynamicRun(Run):
    def __init__(self):
        super().__init__({'case_id': 'dynamic'})
        self.calls = []

    def get_input(self, *, full=False):
        self.calls.append('input')
        if len(self.history) == 2:
            self.state = 'completed'
            return None
        payload = 'initial' if not self.history else self.history[-1]['output']
        self._current = Input(str(len(self.history)), payload)
        return self._current

    def submit(self, output=None, *, status='completed', error=None):
        self.calls.append(('submit', output, status, error))
        return super().submit(output, status=status, error=error)

    def judge(self):
        self.calls.append('judge')
        return Report('pass')


def test_loop_orders_dynamic_inputs_and_judges_once():
    run = DynamicRun()
    async def invoke(item):
        run.calls.append(('invoke', item.payload))
        return {'status': 'succeeded', 'output': item.payload + '-output'}
    report = asyncio.run(drive_run(run, invoke))
    assert report.status == 'pass'
    assert run.calls == ['input', ('invoke', 'initial'),
        ('submit', 'initial-output', 'completed', None), 'input',
        ('invoke', 'initial-output'), ('submit', 'initial-output-output', 'completed', None),
        'input', 'judge']


@pytest.mark.parametrize('status,expected', [('failed', 'failed'), ('timeout', 'timeout'), ('cancelled', 'aborted')])
def test_native_failure_is_submitted_before_next_input(status, expected):
    run = DynamicRun()
    async def invoke(item):
        return {'status': status, 'error': 'original SDK-independent error'}
    asyncio.run(drive_run(run, invoke))
    assert all(row['status'] == expected and row['error'] == 'original SDK-independent error' for row in run.history)


def test_submit_report_is_not_judged_again():
    run = DynamicRun()
    submit = run.submit
    def auto_judge(*args, **kwargs):
        submit(*args, **kwargs)
        return Report('issue') if len(run.history) == 2 else None
    run.submit = auto_judge
    async def invoke(item):
        return {'status': 'succeeded', 'output': 'done'}
    assert asyncio.run(drive_run(run, invoke)).status == 'issue'
    assert 'judge' not in run.calls


def test_submission_exception_is_not_retried_or_judged():
    run = DynamicRun()
    def fail(**kwargs):
        run.calls.append('submit-failed')
        raise ConnectionError('request acceptance unknown')
    run.submit = fail
    async def invoke(item):
        return {'status': 'succeeded', 'output': 'done'}
    with pytest.raises(ConnectionError, match='acceptance unknown'):
        asyncio.run(drive_run(run, invoke))
    assert run.calls == ['input', 'submit-failed']


def test_repeated_input_id_is_rejected_before_second_invocation():
    run, invoked = DynamicRun(), []
    run.get_input = lambda **kwargs: Input('same', 'task')
    run.submit = lambda **kwargs: None
    async def invoke(item):
        invoked.append(item)
        return {'status': 'succeeded', 'output': 'done'}
    with pytest.raises(ValueError, match='distinct'):
        asyncio.run(drive_run(run, invoke))
    assert len(invoked) == 1
