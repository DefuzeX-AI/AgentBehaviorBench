"""Offline ACP peer used to verify private storage with the real ACP adapter."""
import json
import sys
from echo import Echo

agent = Echo()
session = 'isolated-session'


def send(value):
    print(json.dumps({'jsonrpc': '2.0', **value}), flush=True)


for line in sys.stdin:
    request = json.loads(line)
    method, ident = request.get('method'), request.get('id')
    if method == 'initialize':
        send({'id': ident, 'result': {'protocolVersion': 1, 'agentCapabilities': {}, 'authMethods': []}})
    elif method == 'session/new':
        send({'id': ident, 'result': {'sessionId': session}})
    elif method == 'session/prompt':
        result = agent.invoke(request['params']['prompt'][0]['text'])
        send({'method': 'session/update', 'params': {'sessionId': session, 'update': {
            'sessionUpdate': 'agent_message_chunk', 'content': {'type': 'text', 'text': result}}}})
        send({'id': ident, 'result': {'stopReason': 'end_turn'}})
