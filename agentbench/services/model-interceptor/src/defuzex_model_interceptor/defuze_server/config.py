"""Validate gateway destinations before sending credentials."""
from urllib.parse import urlsplit

ENDPOINTS = frozenset(('/chat/completions', '/responses', '/messages',
                       '/messages/count_tokens', '/responses/input_tokens'))
PROTOCOLS = frozenset(('openai-chat', 'openai-chat-thinking', 'openai-responses',
                       'anthropic-messages', 'anthropic-count-tokens', 'openai-input-tokens'))


def validate(target):
    try:
        parsed = urlsplit(target.base_url)
        port = parsed.port
    except ValueError:
        raise ValueError('Invalid Defuze server URL') from None
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or port == 0
            or not parsed.path.rstrip('/').endswith(('/sdk/models/deepseek', '/sdk/models/minimax'))):
        raise ValueError('Defuze server requires an HTTPS model family URL')
    if target.endpoint_paths is None or any(k not in ENDPOINTS or v != k for k, v in target.endpoint_paths.items()):
        raise ValueError('Defuze server requires supported native endpoint mappings')
    if '/chat/completions' not in target.endpoint_paths:
        raise ValueError('Defuze permission checks require a Chat Completions endpoint')
