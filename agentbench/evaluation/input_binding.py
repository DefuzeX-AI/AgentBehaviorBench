"""Forward SDK payloads unchanged to the existing framework Adapter."""
import json
from pathlib import Path


class InputBinding:
    def __init__(self, contract):
        if contract != {'encoding': 'identity'}:
            raise ValueError('Evaluation currently supports only unchanged SDK payloads')

    @classmethod
    def from_file(cls, path: Path):
        return cls(json.loads(path.read_text(encoding='utf-8')))

    def map(self, payload):
        return payload
