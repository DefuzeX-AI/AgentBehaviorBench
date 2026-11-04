"""Small real stdio MCP peer for ACP session integration tests."""
import json
import os
import sys


def send(value):
    print(json.dumps({'jsonrpc': '2.0', **value}), flush=True)


env_key = sys.argv[sys.argv.index('--env-key') + 1] if '--env-key' in sys.argv else None

for line in sys.stdin:
    request = json.loads(line)
    method = request.get('method')
    ident = request.get('id')
    if method == 'initialize':
        send({'id': ident, 'result': {
            'protocolVersion': '2024-11-05',
            'capabilities': {'tools': {}},
            'serverInfo': {'name': 'abb-issue-249-fixture', 'version': '1'},
        }})
    elif method == 'notifications/initialized':
        continue
    elif method == 'tools/list':
        send({'id': ident, 'result': {'tools': [{
            'name': 'echo',
            'description': 'Return supplied text or one fixture environment value.',
            'inputSchema': {
                'type': 'object',
                'properties': {'text': {'type': 'string'}},
                'required': ['text'],
            },
        }]}})
    elif method == 'tools/call':
        text = request.get('params', {}).get('arguments', {}).get('text', '')
        if text == 'echo-secret':
            text = os.environ.get(env_key, '') if env_key else ''
        send({'id': ident, 'result': {'content': [{'type': 'text', 'text': text}]}})
    else:
        send({'id': ident, 'error': {'code': -32601, 'message': 'Method not found'}})
