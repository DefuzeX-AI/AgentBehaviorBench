"""Issue #10: LangGraph routing signals must close spans without ERROR."""
import json
from uuid import uuid4

import pytest
from langgraph.errors import GraphBubbleUp
from opentelemetry.sdk.trace import TracerProvider

from agentbench.observe.invocation import InvocationObservation


@pytest.mark.parametrize('control_flow', [True, False])
def test_live_callback_distinguishes_control_flow(tmp_path, control_flow):
    provider = TracerProvider()
    observed = InvocationObservation(tmp_path, 'invoke', 'session', 'langgraph', provider=provider)
    observed.store.record('execution_start', input='task')
    callback = observed.callbacks[0]
    identity = uuid4()
    callback.on_chain_start({'name': 'route'}, {}, run_id=identity)
    error = GraphBubbleUp('route to parent') if control_flow else ValueError('real failure')
    callback.on_chain_error(error, run_id=identity)
    observed.store.record('execution_end', output='done')
    observed.close()
    provider.shutdown()
    spans = [json.loads(line)['data'] for line in (tmp_path / 'otel.jsonl').read_text().splitlines()]
    route = next(span for span in spans if span['name'] == 'route')
    assert (route['status']['status_code'] == 'ERROR') is not control_flow
    events = [json.loads(line)['event'] for line in (tmp_path / 'framework.jsonl').read_text().splitlines()]
    assert ('span_error' in events) is not control_flow
    assert json.loads((tmp_path / 'otel-status.json').read_text())['unfinished_spans'] == 0


def test_real_tool_arguments_result_and_call_id_reach_kuma(tmp_path):
    from langchain_core.tools import tool
    from kuma import to_json
    from tests.sdk_fixtures.issue_run import sdk_run

    @tool
    def add(left: int, right: int) -> int:
        """Add two integers locally."""
        return left + right

    with sdk_run(tmp_path/'repo', ['Add 2 and 3']) as (run, provider):
        run.get_input(full=True)
        observed = InvocationObservation(tmp_path/'observe', 'invoke', run.run_id, 'langgraph', provider=provider)
        observed.store.record('execution_start', input='Add 2 and 3')
        actual = add.invoke({'type': 'tool_call', 'name': 'add', 'id': 'actual-tool-call', 'args': {'left': 2, 'right': 3}},
                            config=observed.config())
        observed.store.record('execution_end', output=actual.content)
        observed.close()
        run.submit(output=actual.content)
        submission = to_json(run.history[0].submission)
        tool_span, = [s for s in submission['extensions']['trace_evidence']['spans']
                      if s['attributes'].get('gen_ai.operation.name') == 'execute_tool']
        assert tool_span['tool_content_status'] == {'arguments': 'present', 'result': 'present'}
        assert tool_span['attributes']['gen_ai.tool.call.arguments'] == {'left': 2, 'right': 3}
        assert tool_span['attributes']['gen_ai.tool.call.result'] == actual.content
        assert tool_span['attributes']['gen_ai.tool.call.id'] == 'actual-tool-call'
