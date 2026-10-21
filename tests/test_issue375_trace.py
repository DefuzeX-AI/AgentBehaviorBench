"""Issue #375: actual native typed tool arguments survive SDK trace capture."""
from types import SimpleNamespace
import pytest

def test_live_typed_tool_arguments_reach_kuma(tmp_path):
 from typing import Any
 from langchain_core.tools import tool
 from langchain_core.messages import HumanMessage
 from kuma import to_json
 from tests.sdk_fixtures.issue_run import sdk_run
 from agentbench.observe.invocation import InvocationObservation

 @tool
 def inspect_state(function_name: str, state: dict[str, Any]) -> str:
  """Inspect actual injected state without invoking a model."""
  assert state['messages'][0].content=='Inspect classify'
  return 'actual tool result: '+function_name

 with sdk_run(tmp_path/'repo',['Inspect classify']) as (run,provider):
  run.get_input(full=True)
  observed=InvocationObservation(tmp_path/'observe','invoke',run.run_id,'langgraph',provider=provider)
  observed.store.record('execution_start',input='Inspect classify')
  actual=inspect_state.invoke({'type':'tool_call','name':'inspect_state','id':'actual-typed-call','args':{
   'function_name':'classify','state':{'messages':[HumanMessage(content='Inspect classify')],'api_key':'fixture-secret'}}},config=observed.config())
  observed.store.record('execution_end',output=actual.content);observed.close();run.submit(output=actual.content)
  spans=to_json(run.history[0].submission)['extensions']['trace_evidence']['spans']
  tool_span,=[x for x in spans if x['attributes'].get('gen_ai.operation.name')=='execute_tool']
  assert tool_span['tool_content_status']=={'arguments':'present','result':'present'}
  arguments=tool_span['attributes']['gen_ai.tool.call.arguments']
  assert arguments['function_name']=='classify'
  assert arguments['state']['messages'][0]['content']=='Inspect classify'
  assert arguments['state']['api_key']=='[REDACTED]'
  assert tool_span['attributes']['gen_ai.tool.call.result']==actual.content


def test_unsupported_tool_value_is_still_omitted():
 from agentbench.observe.otel.session import OtelSession
 class Exporter:
  secrets=()
  def __init__(self):self.omissions=[]
  def annotate(self,span,data):self.omissions.append(data)
 exporter=Exporter();span=SimpleNamespace(set_attribute=lambda *args:pytest.fail('Opaque input must remain omitted'))
 OtelSession._tool_content(SimpleNamespace(exporter=exporter),span,'arguments',{'opaque':object()})
 assert exporter.omissions==[{'abb.tool_arguments_omission':'not_json_serializable'}]


@pytest.mark.parametrize('synchronous', [False, True])
def test_real_callback_budget_rejection_leaves_no_unfinished_span(monkeypatch, tmp_path, synchronous):
 """Real LangChain dispatch and real OTel; deterministic model, no HTTP calls."""
 import json
 from langchain_core.language_models.fake_chat_models import FakeListChatModel
 from tests.test_issue375_decompai import bridge, UNIT
 from tests.sdk_fixtures.issue_run import sdk_run
 from agentbench.observe.invocation import InvocationObservation
 monkeypatch.syspath_prepend(str(UNIT/'bindings'))
 monkeypatch.setattr(bridge, 'parse_input', lambda value: ('inspect', tmp_path/'binary'))
 monkeypatch.setattr(bridge, 'upstream_system_prompt', lambda: 'Native prompt fixture')
 monkeypatch.setenv('DECOMPAI_MAX_CALLS', '2')
 model = FakeListChatModel(responses=['Observed offline response'])
 class Graph:
  async def ainvoke(self, state, config, **kwargs):
   for _ in range(3):
    if synchronous:
     model.invoke(state['messages'], config=config)
    else:
     await model.ainvoke(state['messages'], config=config)
   pytest.fail('Third model dispatch must be rejected')
 native = SimpleNamespace(utils=SimpleNamespace(create_session_for_binary=lambda path: str(tmp_path)),
                          graph=Graph(), model_context_length=128000)
 monkeypatch.setattr(bridge, '_native', lambda: native)
 with sdk_run(tmp_path/'repo', ['inspect']) as (run, provider):
  run.get_input(full=True)
  observed = InvocationObservation(tmp_path/'observe', 'invoke', run.run_id, 'langgraph', provider=provider)
  observed.store.record('execution_start', input='inspect')
  try:
   with pytest.raises(RuntimeError, match='Deployment model-call budget exhausted'):
    bridge.create_graph().invoke('inspect', config=observed.config())
  finally:
   observed.store.record('execution_error', error='Deployment model-call budget exhausted')
   observed.close()
  status = json.loads((tmp_path/'observe/otel-status.json').read_text())
  assert status == {'status': 'complete', 'unfinished_spans': 0, 'error': None}
  events = [json.loads(line) for line in (tmp_path/'observe/framework.jsonl').read_text().splitlines()]
  starts = [event for event in events if event.get('event') == 'span_start' and event.get('data', {}).get('kind') == 'llm']
  assert len(starts) == 2, 'Rejected third attempt must not open a phantom model span'
