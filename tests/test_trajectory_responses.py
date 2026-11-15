"""Responses stream evidence survives missing final responses and done events."""

def test_responses_deltas_and_done_replace_instead_of_duplicate():
    from agentbench.trajectory.content import model_output
    events = [
        {'type': 'response.output_item.added', 'output_index': 0, 'item': {'type': 'message', 'content': []}},
        {'type': 'response.output_text.delta', 'output_index': 0, 'content_index': 0, 'delta': '你好'},
        {'type': 'response.output_text.delta', 'output_index': 0, 'content_index': 0, 'delta': '世界'},
        {'type': 'response.output_item.added', 'output_index': 1, 'item': {'type': 'function_call', 'call_id': 'tool', 'name': 'sum', 'arguments': ''}},
        {'type': 'response.function_call_arguments.delta', 'output_index': 1, 'delta': '{"a":'},
        {'type': 'response.function_call_arguments.delta', 'output_index': 1, 'delta': '1}'},
    ]
    partial = model_output({'events': events})
    assert partial['text'] == '你好世界'
    assert partial['tool_calls'][0]['arguments'] == {'a': 1}
    events.append({'type': 'response.output_item.done', 'output_index': 0,
                   'item': {'type': 'message', 'content': [{'type': 'output_text', 'text': '你好世界'}]}})
    assert model_output({'events': events}) == partial
