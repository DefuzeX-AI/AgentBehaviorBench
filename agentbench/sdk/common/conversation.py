"""Case-local context delivery, independent of the SDK and Agent framework."""
from copy import deepcopy
import json


class Conversation:
    """Keep only this Case's successful exchanges; never summarize silently."""

    def __init__(self, settings=None):
        settings = dict(settings or {})
        if set(settings) - {'mode', 'input_key', 'history_key', 'max_chars'}:
            raise ValueError('Unknown conversation setting')
        self.mode = settings.get('mode', 'none')
        if self.mode not in ('none', 'native', 'messages', 'text'):
            raise ValueError('Unsupported conversation mode')
        self.input_key = settings.get('input_key')
        self.history_key = settings.get('history_key')
        for key in (self.input_key, self.history_key):
            if key is not None and (not isinstance(key, str) or not key.strip()):
                raise ValueError('Conversation field names must be non-empty strings')
        if self.history_key and self.mode != 'messages':
            raise ValueError('history_key requires messages mode')
        self.max_chars = settings.get('max_chars', 1_000_000)
        if type(self.max_chars) is not int or self.max_chars < 1:
            raise ValueError('Conversation max_chars must be a positive integer')
        self.messages = []
        self.pending = None

    def prepare(self, payload):
        if self.mode in ('none', 'native'):
            return payload
        if not isinstance(payload, str):
            raise ValueError('Conversation augmentation requires a text SDK input')
        self.pending = deepcopy(self.messages) + [{'role': 'user', 'content': payload}]
        value = self.pending if self.mode == 'messages' else (
            'Previous conversation (JSON):\n' + json.dumps(self.messages, ensure_ascii=False)
            + '\n\nCurrent user message:\n' + payload)
        value = {self.input_key: value} if self.input_key else value
        if len(json.dumps(value, ensure_ascii=False)) > self.max_chars:
            raise ValueError('Conversation exceeds max_chars; history was not truncated')
        return deepcopy(value)

    def commit(self, result):
        if self.mode in ('none', 'native') or result.get('status') != 'succeeded':
            return
        if self.pending is None:
            raise ValueError('No conversation input is pending')
        if self.history_key:
            raw = result.get('raw_output')
            history = raw.get(self.history_key) if isinstance(raw, dict) else None
            if not isinstance(history, list) or not history or any(not isinstance(m, dict) for m in history):
                raise ValueError('Configured native message history is missing from raw_output')
            # Full native history preserves tool calls/results and message IDs.
            self.messages = deepcopy(history)
        else:
            answer = result['output']
            if not isinstance(answer, str):
                answer = json.dumps(answer, ensure_ascii=False)
            self.messages = self.pending + [{'role': 'assistant', 'content': answer}]
        self.pending = None
