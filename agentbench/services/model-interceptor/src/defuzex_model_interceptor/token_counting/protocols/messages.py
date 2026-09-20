"""Messages input-token counting envelope."""


class MessagesProtocol:
    name = 'anthropic-count-tokens'

    def normalize(self, body):
        from . import UnsupportedInput, ensure_text_input
        if body.get('mcp_servers'):
            raise UnsupportedInput('Remote MCP context cannot be counted locally')
        if not isinstance(body.get('messages'), list):
            raise ValueError('messages must be an array')
        ensure_text_input(body['messages'])
        ensure_text_input(body.get('system'))
        if not isinstance(body.get('tools', []), list):
            raise ValueError('tools must be an array')
        return {k: body[k] for k in ('messages', 'system', 'tools', 'output_config') if k in body}

    def response(self, tokens):
        return {'input_tokens': tokens}
