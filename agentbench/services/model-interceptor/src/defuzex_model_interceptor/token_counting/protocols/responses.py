"""Responses input-token counting envelope."""


class ResponsesProtocol:
    name = 'openai-input-tokens'

    def normalize(self, body):
        from . import UnsupportedInput, ensure_text_input
        if body.get('conversation') or body.get('previous_response_id'):
            raise UnsupportedInput('Server-held conversation cannot be counted locally')
        value = body.get('input')
        if not isinstance(value, (str, list)):
            raise ValueError('input must be text or an array')
        ensure_text_input(value)
        if 'instructions' in body and not isinstance(body['instructions'], str):
            raise ValueError('instructions must be text')
        if not isinstance(body.get('tools', []), list):
            raise ValueError('tools must be an array')
        return {k: body[k] for k in ('input', 'instructions', 'tools', 'text') if k in body}

    def response(self, tokens):
        return {'object': 'response.input_tokens', 'input_tokens': tokens}
