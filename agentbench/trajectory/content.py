"""Normalize provider request/response bodies into complete step content.

Streaming chunks are merged into one message; nothing is summarized. Values
larger than the hard cap are replaced by a labelled digest, never silently cut.
"""
import hashlib
import json
import os

DEFAULT_MAX_VALUE_BYTES = 1024 * 1024
HEAD_BYTES = 64 * 1024


def max_value_bytes(environ=None):
    raw = (environ if environ is not None else os.environ).get('ABB_TRAJECTORY_MAX_VALUE_BYTES')
    try:
        return max(HEAD_BYTES, int(raw)) if raw else DEFAULT_MAX_VALUE_BYTES
    except ValueError:
        return DEFAULT_MAX_VALUE_BYTES


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def bounded(value, limit):
    """Replace oversized strings with an explicit marker; structure is kept."""
    if isinstance(value, str):
        raw = value.encode('utf-8', 'surrogatepass')
        if len(raw) <= limit:
            return value
        return {'truncated': True, 'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                'head': raw[:HEAD_BYTES].decode('utf-8', 'replace')}
    if isinstance(value, dict):
        return {key: bounded(item, limit) for key, item in value.items()}
    if isinstance(value, list):
        return [bounded(item, limit) for item in value]
    return value


def _objects(value):
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def model_input(payload):
    """Split a provider request into the parts a reader needs by name."""
    if not isinstance(payload, dict):
        return {'raw': payload}
    known = ('messages', 'system', 'tools', 'model', 'input', 'instructions')
    value = {key: payload[key] for key in known if key in payload}
    parameters = {key: item for key, item in payload.items() if key not in known}
    if parameters:
        value['parameters'] = parameters
    return value


def _tool_call(identifier, name, arguments):
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments) if arguments.strip() else {}
        except ValueError:
            pass
    return {'id': identifier, 'name': name, 'arguments': arguments}


def _merge_openai_chunks(chunks):
    text, reasoning, calls, finish, usage, model = [], [], {}, None, None, None
    for chunk in chunks:
        usage = chunk.get('usage') or usage
        model = chunk.get('model') or model
        for choice in _objects(chunk.get('choices')):
            delta = choice.get('delta') if isinstance(choice.get('delta'), dict) else {}
            if isinstance(delta.get('content'), str):
                text.append(delta['content'])
            for key in ('reasoning_content', 'reasoning'):
                if isinstance(delta.get(key), str):
                    reasoning.append(delta[key])
            for call in _objects(delta.get('tool_calls')):
                slot = calls.setdefault(call.get('index', len(calls)), {'id': None, 'name': None, 'arguments': ''})
                slot['id'] = call.get('id') or slot['id']
                function = call.get('function') if isinstance(call.get('function'), dict) else {}
                slot['name'] = function.get('name') or slot['name']
                slot['arguments'] += function.get('arguments') or ''
            finish = choice.get('finish_reason') or finish
    return {'text': ''.join(text), 'reasoning': ''.join(reasoning) or None,
            'tool_calls': [_tool_call(c['id'], c['name'], c['arguments']) for _, c in sorted(calls.items())],
            'finish_reason': finish, 'usage': usage, 'model': model}


def _merge_anthropic_events(events):
    blocks, finish, usage, model = {}, None, {}, None
    for event in events:
        kind = event.get('type')
        if kind == 'message_start' and isinstance(event.get('message'), dict):
            model = event['message'].get('model')
            usage.update(event['message'].get('usage') or {})
        elif kind == 'content_block_start':
            blocks[event.get('index')] = dict(event.get('content_block') or {})
            blocks[event['index']].setdefault('_json', '')
        elif kind == 'content_block_delta':
            block = blocks.setdefault(event.get('index'), {'type': 'text', 'text': '', '_json': ''})
            delta = event.get('delta') or {}
            if delta.get('type') == 'text_delta':
                block['text'] = block.get('text', '') + delta.get('text', '')
            elif delta.get('type') == 'thinking_delta':
                block['thinking'] = block.get('thinking', '') + delta.get('thinking', '')
            elif delta.get('type') == 'input_json_delta':
                block['_json'] += delta.get('partial_json', '')
        elif kind == 'message_delta':
            finish = (event.get('delta') or {}).get('stop_reason') or finish
            usage.update(event.get('usage') or {})
    content = []
    for _, block in sorted(blocks.items(), key=lambda item: item[0] if isinstance(item[0], int) else -1):
        if block.get('type') == 'tool_use' and block.get('_json'):
            block['input'] = block['_json']
        block.pop('_json', None)
        content.append(block)
    return _from_anthropic_content(content, finish, usage or None, model)


def _from_anthropic_content(content, finish, usage, model):
    text = ''.join(b.get('text', '') for b in content if b.get('type') == 'text')
    thinking = ''.join(b.get('thinking', '') for b in content if b.get('type') == 'thinking')
    calls = [_tool_call(b.get('id'), b.get('name'), b.get('input')) for b in content if b.get('type') == 'tool_use']
    return {'text': text, 'reasoning': thinking or None, 'tool_calls': calls,
            'finish_reason': finish, 'usage': usage, 'model': model}


def model_output(payload):
    """One complete assistant turn from any supported wire format."""
    if not isinstance(payload, dict):
        return {'text': None, 'reasoning': None, 'tool_calls': [], 'finish_reason': None,
                'usage': None, 'model': None, 'raw': payload}
    events = _objects(payload.get('events'))
    if events:
        if any('choices' in event for event in events):
            return _merge_openai_chunks(events)
        if any(event.get('type') in ('message_start', 'content_block_start', 'content_block_delta') for event in events):
            return _merge_anthropic_events(events)
        completed = next((e['response'] for e in reversed(events)
                          if e.get('type') == 'response.completed' and isinstance(e.get('response'), dict)), None)
        if completed is not None:
            return model_output(completed)
    choices = _objects(payload.get('choices'))
    if choices:
        message = choices[0].get('message') if isinstance(choices[0].get('message'), dict) else {}
        calls = [_tool_call(c.get('id'), (c.get('function') or {}).get('name'), (c.get('function') or {}).get('arguments'))
                 for c in _objects(message.get('tool_calls'))]
        return {'text': message.get('content'), 'reasoning': message.get('reasoning_content') or message.get('reasoning'),
                'tool_calls': calls, 'finish_reason': choices[0].get('finish_reason'),
                'usage': payload.get('usage'), 'model': payload.get('model')}
    if isinstance(payload.get('content'), list) and payload.get('role') == 'assistant':
        return _from_anthropic_content(_objects(payload['content']), payload.get('stop_reason'),
                                       payload.get('usage'), payload.get('model'))
    if isinstance(payload.get('output'), list):
        text, reasoning, calls = [], [], []
        for item in _objects(payload['output']):
            if item.get('type') == 'message':
                text.extend(part.get('text', '') for part in _objects(item.get('content')) if part.get('type') == 'output_text')
            elif item.get('type') == 'function_call':
                calls.append(_tool_call(item.get('call_id'), item.get('name'), item.get('arguments')))
            elif item.get('type') == 'reasoning':
                reasoning.extend(part.get('text', '') for part in _objects(item.get('summary')))
        return {'text': ''.join(text), 'reasoning': ''.join(reasoning) or None, 'tool_calls': calls,
                'finish_reason': payload.get('status'), 'usage': payload.get('usage'), 'model': payload.get('model')}
    return {'text': None, 'reasoning': None, 'tool_calls': [], 'finish_reason': None,
            'usage': None, 'model': payload.get('model'), 'raw': payload}


def framework_output(output):
    """A LangChain generation result: the message the graph actually received."""
    generations = output.get('generations') if isinstance(output, dict) else None
    first = generations[0][0] if isinstance(generations, list) and generations and generations[0] else None
    if not isinstance(first, dict):
        return {'text': None, 'reasoning': None, 'tool_calls': [], 'finish_reason': None,
                'usage': None, 'model': None, 'raw': output}
    message = first.get('message') if isinstance(first.get('message'), dict) else {}
    extra = message.get('additional_kwargs') if isinstance(message.get('additional_kwargs'), dict) else {}
    meta = message.get('response_metadata') if isinstance(message.get('response_metadata'), dict) else {}
    calls = [_tool_call(c.get('id'), c.get('name'), c.get('args')) for c in _objects(message.get('tool_calls'))]
    return {'text': first.get('text') if first.get('text') is not None else message.get('content'),
            'reasoning': extra.get('reasoning_content') or extra.get('reasoning'),
            'tool_calls': calls, 'finish_reason': (first.get('generation_info') or {}).get('finish_reason') or meta.get('finish_reason'),
            'usage': message.get('usage_metadata') or (first.get('generation_info') or {}).get('usage'),
            'model': meta.get('model_name') or (first.get('generation_info') or {}).get('model_name')}


def framework_input(value):
    """LangChain prompts arrive as a list of message lists; keep the first batch whole."""
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], list):
        return {'messages': value[0]}
    if isinstance(value, dict) and 'messages' in value:
        return {'messages': value['messages']}
    return {'messages': value}


def exit_status(output):
    """Terminal exit status recorded by ACP tool evidence, if observed."""
    if isinstance(output, dict):
        for item in _objects(output.get('content')):
            if item.get('type') == 'terminal' and isinstance(item.get('exitStatus'), dict):
                return item['exitStatus']
        for item in output.values():
            found = exit_status(item)
            if found is not None:
                return found
    elif isinstance(output, list):
        for item in output:
            found = exit_status(item)
            if found is not None:
                return found
    return None
