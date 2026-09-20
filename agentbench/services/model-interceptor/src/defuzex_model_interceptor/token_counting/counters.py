"""Deterministic, versioned estimates; never billing or provider ground truth."""
import json
from importlib.metadata import version

# Installed with the image so counting never downloads data during an Agent run.
ENCODINGS = ('cl100k_base', 'o200k_base')
ALGORITHM = 'structured-json-bpe-v1'


def estimate(payload, encoding):
    """Count the canonical input envelope, including tools and message structure.

    Provider prompt rendering and hidden overhead are not public. Encoding the
    structured envelope is reproducible but only an estimate, not an exact count
    or guaranteed upper bound. Never reuse the previous generation's usage.
    """
    import tiktoken
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    tokens = len(tiktoken.get_encoding(encoding).encode(canonical, disallowed_special=()))
    return tokens, f'tiktoken/{version("tiktoken")};{ALGORITHM}'


def preload():
    import tiktoken
    for name in ENCODINGS:
        tiktoken.get_encoding(name)


if __name__ == '__main__':
    preload()
