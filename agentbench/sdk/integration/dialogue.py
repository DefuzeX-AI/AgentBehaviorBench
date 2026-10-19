"""Sequential SDKRun execution; vendor evidence and recovery stay in plugins."""
from agentbench.observe.timing import span
from agentbench.sdk.contracts import SDKRun


def submit_result(run: SDKRun, result):
    """Forward the native result, including an unchanged failure description."""
    if result['status'] == 'succeeded':
        return run.submit(output=result['output'], status='completed')
    status = {'timeout': 'timeout', 'cancelled': 'aborted', 'aborted': 'aborted'}.get(
        result['status'], 'failed')
    return run.submit(status=status, error=result.get('error'))


def judge_run(run: SDKRun):
    """Do not charge for a second Judge when submit already produced a report."""
    report = run.report
    if report is None:
        report = run.judge()
        if report is None:
            report = run.report
    if report is None:
        raise ValueError('SDK finished without a Judge report')
    return report


async def drive_run(run: SDKRun, invoke, *, step=None, before_input=None, judge=True):
    """Drive existing get_input/submit methods in order, with one active input.

    ``invoke(item)`` returns the native result envelope. Advanced plugins can
    supply ``step(run, item, invoke)`` to keep their evidence/submission
    transaction around an invocation; ordinary SDKs need no callbacks. Exceptions
    propagate without retrying generation, submission, or Judge requests.
    """
    seen, submitted_report = set(), None
    while True:
        if before_input is not None:
            before_input()
        with span('Get next input', kind='sdk'):
            item = run.get_input(full=True)
        if item is None:
            break
        if not isinstance(item.input_id, str) or not item.input_id.strip() or item.input_id in seen:
            raise ValueError('SDK inputs must have distinct non-empty IDs within a Run')
        seen.add(item.input_id)
        if step is not None:
            report = await step(run, item, invoke)
        else:
            report = submit_result(run, await invoke(item))
        submitted_report = report
    if not judge:
        return submitted_report
    return submitted_report if submitted_report is not None else judge_run(run)
