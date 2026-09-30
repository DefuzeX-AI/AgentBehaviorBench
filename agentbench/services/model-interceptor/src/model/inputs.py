"""Input requirements for native conversation payloads, without scanning tool schemas."""


def conversation_input(payload):
    """Return the primary modality; mixed text/image conversations require image support.

    Inspect message content only: a tool definition mentioning images is not an
    image input. Unknown content types are rejected instead of classified as text.
    """
    kinds = set()

    def content(value):
        if value is None or isinstance(value, str):
            return
        if not isinstance(value, list):
            raise ValueError('Unsupported conversation content')
        for part in value:
            if not isinstance(part, dict):
                raise ValueError('Unsupported conversation content part')
            kind = part.get('type')
            if kind in ('text', 'input_text', 'output_text', 'refusal', 'thinking', 'redacted_thinking'):
                continue
            if kind in ('image_url', 'input_image', 'image'):
                kinds.add('image')
            elif kind == 'tool_result':
                content(part.get('content'))
            elif kind == 'tool_use':
                continue
            else:
                raise ValueError(f'Unsupported model input content type: {kind!r}')

    messages = payload.get('messages', [])
    if not isinstance(messages, list):
        raise ValueError('messages must be a list')
    for message in messages:
        if not isinstance(message, dict):
            raise ValueError('Invalid conversation message')
        content(message.get('content'))
    entries = payload.get('input', [])
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError('Invalid Responses input item')
            kind = entry.get('type', 'message')
            if kind == 'message':
                content(entry.get('content'))
            elif kind == 'function_call_output':
                content(entry.get('output'))
            elif kind in ('function_call', 'reasoning', 'item_reference'):
                continue
            else:
                raise ValueError(f'Unsupported Responses input item type: {kind!r}')
    elif not isinstance(entries, str):
        raise ValueError('Unsupported Responses input')
    return 'image' if kinds else 'text'
