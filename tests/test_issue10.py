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
