from agentbench.cli.terminal_ui.llm_activity import LLMActivity
from agentbench.cli.terminal_ui.progress import ProgressPrinter
from agentbench.harness.progress import BenchmarkProgress
from agentbench.runtime.interception import TraceEvent


def test_compact_progress_keeps_transitions_and_errors_only():
    lines = []
    activity = LLMActivity(lines.append, live_updates=False)
    activity.compact = True
    activity.case_counts = {'agent': 1}
    printer = ProgressPrinter(lines.append, llm_activity=activity, live_updates=False)
    printer(BenchmarkProgress('case_generation', 'started', agent_id='agent'))
    printer(BenchmarkProgress('case_generation', 'succeeded', agent_id='agent', detail='Validated Input artifacts'))
    activity.show_case_status('agent', 0, 'Running Agent')
    printer(BenchmarkProgress('benchmark_execution', 'started', agent_id='agent', case_index=0))
    base = dict(agent_id='agent', case_index=0, phase='execute', purpose='evaluation')
    activity.emit(TraceEvent('tool_response', dict(base, method='GET', path='/config/', status=200)))
    activity.emit(TraceEvent('tool_request', dict(base, method='POST', path='/sdk/v2/judge/')))
    for _ in range(25):
        activity.emit(TraceEvent('tool_response', dict(base, method='GET', path='/operations/1/', status=200)))
    activity.emit(TraceEvent('llm_request', dict(base, call_id='1', payload={'prompt': 'private preview'})))
    assert len(lines) == 3
    assert 'case 1/1] Generating' in lines[0]
    assert 'Running Agent' in lines[1]
    assert 'Waiting for Judge' in lines[2]
    activity.emit(TraceEvent('tool_response', dict(base, method='POST', path='/judge/', status=401)))
    assert 'HTTP 401' in lines[-1]
    activity.emit(TraceEvent('llm_error', dict(agent_id='agent', case_index=0, error='model unavailable')))
    assert 'model unavailable' in lines[-1]
    activity.close()


def test_generation_poll_does_not_claim_to_wait_for_judge():
    lines = []
    activity = LLMActivity(lines.append, live_updates=False)
    activity.compact = True
    activity.emit(TraceEvent('tool_request', dict(
        agent_id='agent', phase='generate', purpose='evaluation', method='POST', path='/judge/')))
    assert not any('Waiting for Judge' in line for line in lines)
    activity.close()
