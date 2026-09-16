"""Issue #64: a retained Judge verdict is counted, and labelled as host rejected, not "no report"."""
from types import SimpleNamespace

from agentbench.harness.result import CaseResult
from agentbench.cli.terminal_ui.presentation import case_event_status, print_suite_summary

RETAINED = {'received_report': {'status': 'issue', 'report_id': 'judgment_x', 'run_id': 'run_x',
                                'case_id': 'case_x', 'path': 'evaluation/judge/report.json',
                                'host_accepted': False}}


def _suite(*cases):
    item = SimpleNamespace(case_results=cases, requested_case_count=len(cases))
    return SimpleNamespace(items=[item], passed_count=0, failed_count=len(cases), skipped_count=0,
                           selected_count=len(cases))


def test_retained_verdict_is_the_case_judge_status_but_not_accepted():
    case = CaseResult('article-explainer', 0, 'job', 'failed', error_type='RuntimeError',
                      error_message='Container evaluation did not complete', artifacts=RETAINED)
    assert case.judge_status == 'issue'
    assert case.judge_accepted is False
    assert case.execution_status == 'blocked'


def test_summary_counts_the_retained_verdict_and_says_the_host_rejected_it():
    output = []
    case = CaseResult('article-explainer', 0, 'job', 'failed', artifacts=RETAINED)
    print_suite_summary(_suite(case), output.append)
    assert 'Case execution: 0/1 completed | Judge: issue=1 (1 host rejected)' in output[0]
    assert 'no report' not in output[0]


def test_progress_line_shows_the_retained_verdict():
    case = CaseResult('article-explainer', 0, 'job', 'failed', artifacts=RETAINED)
    assert case_event_status({'case_result': case}) == 'blocked | judge=issue (host rejected)'


def test_cases_without_any_verdict_still_read_no_report():
    output = []
    print_suite_summary(_suite(CaseResult('agent', 0, 'job', 'failed', artifacts={})), output.append)
    assert output[0].endswith('Judge: no report')
    assert case_event_status({'case_result': CaseResult('agent', 0, 'job', 'failed')}) == 'blocked'


def test_malformed_retained_report_is_not_a_verdict():
    case = CaseResult('agent', 0, 'job', 'failed', artifacts={'received_report': {'status': 3}})
    assert case.judge_status is None
