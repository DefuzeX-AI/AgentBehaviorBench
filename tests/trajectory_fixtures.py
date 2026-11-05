"""Self-contained attempt directories for trajectory tests; no bundled Agents."""
import json
from pathlib import Path

CASE = 'case_fixture'
INPUT = 'step-1'
PROMPT = 'List the files, then answer.'


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows), encoding='utf-8')


def _framework(event, timestamp, **data):
    return {'schema': 'abb.observe.event.v1', 'run_id': 'run', 'source': 'framework', 'event': event,
            'timestamp': timestamp, 'data': {'case_id': CASE, 'input_id': INPUT, 'agent_id': 'alpha', **data}}


def _wire(event, timestamp, call_id, **data):
    return {'schema': 'abb.observe.event.v1', 'run_id': 'run', 'source': 'interceptor', 'event': event,
            'timestamp': timestamp, 'data': {'call_id': call_id, 'case_id': CASE, 'host': 'api.example',
                                             'path': '/v1/chat/completions', 'method': 'POST', **data}}


def _step_files(root, steps_prefix, framework, result='done'):
    folder = root / steps_prefix / '0001'
    write_json(folder / 'input.json', {'run_id': 'sdk-run', 'case_id': CASE, 'input_id': INPUT, 'index': 0,
                                       'payload_type': 'text', 'payload': PROMPT})
    write_json(folder / 'request.json', {'schema': 'abb.invocation.v1', 'run_id': 'run', 'session_id': 'sdk-run',
                                         'observation_context': {'case_id': CASE, 'input_id': INPUT},
                                         'agent_id': 'alpha', 'framework': framework, 'input': PROMPT})
    write_json(folder / 'result.json', {'schema': 'abb.result.v1', 'run_id': 'run', 'case_id': CASE,
                                        'input_id': INPUT, 'agent_id': 'alpha', 'status': 'succeeded', 'output': result})
    write_json(folder / 'otel-status.json', {'status': 'complete'})
    return folder


def langgraph_attempt(root, *, layout='steps', drop_wire_response=False):
    """Two model calls; the first emits two parallel tools, the second answers."""
    root = Path(root)
    prefix = 'steps' if layout == 'steps' else 'evaluation/inputs'
    network = 'logs/network.jsonl' if layout == 'steps' else 'network.jsonl'
    write_json(root / 'run.json', {'schema': 'abb.evaluate.run.v1', 'run_id': 'run', 'agent_id': 'alpha',
                                   'case_id': CASE, 'status': 'succeeded', 'phase': 'execute'})
    write_json(root / ('case.json' if layout == 'steps' else 'evaluation/case.json'),
               {'case_id': CASE, 'inputs': [{'input_id': INPUT, 'payload': PROMPT}]})
    folder = _step_files(root, prefix, 'langgraph')
    system = 'You are alpha.'
    first_messages = [{'role': 'system', 'content': system}, {'role': 'user', 'content': PROMPT}]
    tools = [{'type': 'function', 'function': {'name': 'ls', 'parameters': {}}},
             {'type': 'function', 'function': {'name': 'cat', 'parameters': {}}}]
    calls = [{'id': 'call_ls', 'type': 'function', 'function': {'name': 'ls', 'arguments': '{"path": "."}'}},
             {'id': 'call_cat', 'type': 'function', 'function': {'name': 'cat', 'arguments': '{"path": "a.txt"}'}}]
    second_messages = first_messages + [{'role': 'assistant', 'content': None, 'tool_calls': calls},
                                        {'role': 'tool', 'tool_call_id': 'call_ls', 'content': 'a.txt'},
                                        {'role': 'tool', 'tool_call_id': 'call_cat', 'content': 'hello'}]
    meta = {'langgraph_checkpoint_ns': 'model:1', 'langgraph_node': 'model'}
    ai_message = {'type': 'ai', 'content': '', 'tool_calls': [{'id': 'call_ls', 'name': 'ls', 'args': {'path': '.'}},
                                                               {'id': 'call_cat', 'name': 'cat', 'args': {'path': 'a.txt'}}]}
    framework = [
        _framework('execution_start', '2026-01-01T00:00:00+00:00', input=PROMPT),
        _framework('span_start', '2026-01-01T00:00:01+00:00', kind='chain', span_id='node-1', parent_span_id=None,
                   name='model', metadata=meta),
        _framework('span_start', '2026-01-01T00:00:01+00:00', kind='llm', span_id='llm-1', parent_span_id='node-1',
                   name='ChatOpenAI', input=[[{'type': 'system', 'content': system}, {'type': 'human', 'content': PROMPT}]],
                   metadata=meta),
        _framework('span_end', '2026-01-01T00:00:02+00:00', span_id='llm-1',
                   output={'generations': [[{'text': '', 'generation_info': {'finish_reason': 'tool_calls'},
                                             'message': {'content': '', 'response_metadata': {'model_name': 'm'}}}]]}),
        _framework('span_end', '2026-01-01T00:00:02+00:00', span_id='node-1', output=[{'update': {'messages': [ai_message]}}]),
        _framework('span_start', '2026-01-01T00:00:03+00:00', kind='tool', span_id='tool-ls', parent_span_id='tools-1',
                   name='ls', tool_call_id='call_ls', input={'path': '.'}, metadata={'langgraph_node': 'tools'}),
        _framework('span_start', '2026-01-01T00:00:03+00:00', kind='tool', span_id='tool-cat', parent_span_id='tools-1',
                   name='cat', tool_call_id='call_cat', input={'path': 'a.txt'}, metadata={'langgraph_node': 'tools'}),
        _framework('span_end', '2026-01-01T00:00:04+00:00', span_id='tool-ls', tool_call_id='call_ls',
                   tool_status='success', output='a.txt'),
        _framework('span_end', '2026-01-01T00:00:04+00:00', span_id='tool-cat', tool_call_id='call_cat',
                   tool_status='success', output='hello'),
        _framework('span_start', '2026-01-01T00:00:05+00:00', kind='llm', span_id='llm-2', parent_span_id='node-2',
                   name='ChatOpenAI', input=[[{'type': 'human', 'content': PROMPT}]], metadata=meta),
        _framework('span_end', '2026-01-01T00:00:06+00:00', span_id='llm-2',
                   output={'generations': [[{'text': 'The file says hello.', 'generation_info': {'finish_reason': 'stop'},
                                             'message': {'content': 'The file says hello.'}}]]}),
        _framework('execution_end', '2026-01-01T00:00:07+00:00', output='The file says hello.'),
    ]
    write_jsonl(folder / 'framework.jsonl', framework)
    wire = [_wire('llm_request', '2026-01-01T00:00:01+00:00', 'call-1', framework_span_id='llm-1', model='m',
                  payload={'model': 'm', 'messages': first_messages, 'tools': tools, 'temperature': 0})]
    if not drop_wire_response:
        wire.append(_wire('llm_response', '2026-01-01T00:00:02+00:00', 'call-1', framework_span_id='llm-1', status=200,
                          latency_ms=10, payload={'id': 'r1', 'model': 'm', 'choices': [{'index': 0, 'finish_reason': 'tool_calls',
                          'message': {'role': 'assistant', 'content': None, 'tool_calls': calls}}],
                          'usage': {'prompt_tokens': 10, 'completion_tokens': 5}}))
    else:
        wire.append(_wire('llm_error', '2026-01-01T00:00:02+00:00', 'call-1', framework_span_id='llm-1',
                          error_code='transport_error', error='Client disconnected.'))
    wire.append(_wire('llm_request', '2026-01-01T00:00:05+00:00', 'call-2', framework_span_id='llm-2', model='m',
                      payload={'model': 'm', 'messages': second_messages, 'tools': tools}))
    wire.append(_wire('llm_response', '2026-01-01T00:00:06+00:00', 'call-2', framework_span_id='llm-2', status=200,
                      latency_ms=10, payload={'events': [
                          {'id': 'r2', 'model': 'm', 'choices': [{'index': 0, 'delta': {'role': 'assistant', 'content': 'The file '}}]},
                          {'id': 'r2', 'model': 'm', 'choices': [{'index': 0, 'delta': {'content': 'says hello.'}, 'finish_reason': 'stop'}],
                           'usage': {'prompt_tokens': 20, 'completion_tokens': 4}}]}))
    write_jsonl(root / network, wire)
    return root


def acp_attempt(root):
    """One observe-mode model call emitting a terminal tool whose exit status was observed."""
    root = Path(root)
    write_json(root / 'run.json', {'schema': 'abb.evaluate.run.v1', 'run_id': 'run', 'agent_id': 'alpha',
                                   'case_id': CASE, 'status': 'succeeded', 'phase': 'execute'})
    folder = _step_files(root, 'steps', 'acp')
    write_json(folder / 'acp-summary.json', {'coverage': 'protocol_events', 'internal_model_spans': 'not_observed'})
    write_jsonl(folder / 'framework.jsonl', [
        _framework('span_start', '2026-01-01T00:00:03+00:00', kind='tool', span_id='acp:call_sh', parent_span_id=None,
                   name='exec', tool_call_id='call_sh', input=None),
        _framework('span_update', '2026-01-01T00:00:03.5+00:00', span_id='acp:call_sh', input={'command': 'exit 3'}),
        _framework('span_end', '2026-01-01T00:00:04+00:00', span_id='acp:call_sh', tool_call_id='call_sh',
                   tool_status='succeeded', output={'content': [{'type': 'terminal', 'terminalId': 't1', 'output': 'x\n',
                                                                 'exitStatus': {'exitCode': 3, 'signal': None}}]}),
        _framework('span_start', '2026-01-01T00:00:05+00:00', kind='tool', span_id='acp:direct', parent_span_id=None,
                   name='read', tool_call_id='call_direct', input={'path': 'a'}),
        _framework('span_end', '2026-01-01T00:00:06+00:00', span_id='acp:direct', tool_call_id='call_direct',
                   tool_status='succeeded', output={'content': [{'type': 'text', 'text': 'A'}]}),
    ])
    write_jsonl(root / 'logs/network.jsonl', [
        _wire('llm_request', '2026-01-01T00:00:01+00:00', 'call-1', mode='observe', native_session_id='s1',
              payload={'model': 'glm', 'messages': [{'role': 'user', 'content': PROMPT}], 'tools': []}),
        _wire('llm_response', '2026-01-01T00:00:02+00:00', 'call-1', mode='observe', native_session_id='s1', status=200,
              payload={'events': [
                  {'id': 'r1', 'model': 'glm', 'choices': [{'index': 0, 'delta': {'role': 'assistant', 'reasoning_content': 'think'}}]},
                  {'id': 'r1', 'model': 'glm', 'choices': [{'index': 0, 'delta': {'tool_calls': [
                      {'index': 0, 'id': 'call_sh', 'type': 'function', 'function': {'name': 'exec', 'arguments': '{"command": '}}]}}]},
                  {'id': 'r1', 'model': 'glm', 'choices': [{'index': 0, 'delta': {'tool_calls': [
                      {'index': 0, 'function': {'arguments': '"exit 3"}'}}]}, 'finish_reason': 'tool_calls'}]}]}),
    ])
    return root
