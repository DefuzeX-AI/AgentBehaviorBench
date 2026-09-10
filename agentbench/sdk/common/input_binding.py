"""Forward SDK payloads unchanged to the existing framework Adapter."""
import json
from pathlib import Path
from .conversation import Conversation


class InputBinding:
    def __init__(self, contract):
        if contract.get('encoding') != 'identity' or set(contract) - {'encoding', 'conversation'}:
            raise ValueError('Evaluation currently supports only unchanged SDK payloads')
        settings = contract.get('conversation', {})
        if not isinstance(settings, dict):
            raise ValueError('conversation must be an object')
        Conversation(settings)
        self.conversation_settings = settings

    @classmethod
    def from_file(cls, path: Path):
        return cls(json.loads(path.read_text(encoding='utf-8')))

    def map(self, payload):
        return payload

    def new_conversation(self):
        return Conversation(self.conversation_settings)
