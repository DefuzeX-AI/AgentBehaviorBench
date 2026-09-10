"""Named driver registry: adding a client does not change the runner."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Case:
    name: str
    run: object
    streaming: bool

CASES = {}

def register(name, *, streaming=False):
    def decorate(run):
        if name in CASES:
            raise ValueError("Duplicate probe case: " + name)
        CASES[name] = Case(name, run, streaming)
        return run
    return decorate

def load_cases():
    from . import openai_client, google_client, anthropic_client, ollama_client, raw_http
    return dict(CASES)

