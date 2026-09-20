"""Request/response shapes, independent of model-specific counting algorithms."""
from .base import TokenCountProtocol
from .messages import MessagesProtocol
from .responses import ResponsesProtocol

PROTOCOLS: dict[str, TokenCountProtocol] = {p.name: p for p in (MessagesProtocol(), ResponsesProtocol())}


class UnsupportedInput(ValueError):
    pass


def ensure_text_input(value):
    """Reject media and unresolved references instead of counting their URL/base64.

    Tool schemas are deliberately validated separately: a schema may contain a
    property named image or file without carrying any media input.
    """
    if isinstance(value, list):
        for item in value:
            ensure_text_input(item)
    elif isinstance(value, dict):
        kind = value.get('type', '')
        if kind in {'image', 'image_url', 'input_image', 'audio', 'input_audio',
                    'input_file', 'file', 'document', 'video', 'item_reference',
                    'tool_reference', 'redacted_thinking', 'compaction'}:
            raise UnsupportedInput('Local estimator does not support this input block')
        if value.get('encrypted_content'):
            raise UnsupportedInput('Encrypted context cannot be counted locally')
        for item in value.values():
            ensure_text_input(item)
