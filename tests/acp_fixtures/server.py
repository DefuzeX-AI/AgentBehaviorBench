"""Small real stdio peer; deliberately independent of the client SDK implementation."""
import json
import os
import sys
import time
import uuid

session = uuid.uuid4().hex
turn = 0


def send(value):
    print(json.dumps({'jsonrpc': '2.0', **value}), flush=True)


def notify(text):
    send({'method': 'session/update', 'params': {'sessionId': session,
          'update': {'sessionUpdate': 'agent_message_chunk', 'content': {'type': 'text', 'text': text}}}})


for line in sys.stdin:
    request = json.loads(line)
    method, params = request.get('method'), request.get('params', {})
    ident = request.get('id')
    if method == 'initialize':
        send({'id': ident, 'result': {'protocolVersion': 1, 'agentCapabilities': {},
                                    'authMethods': [{'id': 'test', 'name': 'Test login'}]}})
    elif method == 'authenticate':
        send({'id': ident, 'error': {'code': -32000, 'message': 'Synthetic authentication rejected'}})
    elif method == 'session/new':
        send({'id': ident, 'result': {'sessionId': session}})
    elif method == 'session/prompt':
        turn += 1
        text = params['prompt'][0]['text']
        if text == 'child':
            import subprocess
            child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
            notify(str(child.pid))
            send({'id': ident, 'result': {'stopReason': 'end_turn'}})
            continue
        if text == 'disconnect':
            sys.exit(3)
        if text == 'malformed':
            print('{invalid json', flush=True)
            time.sleep(30)
        if text == 'hang':
            time.sleep(30)
        if text == 'stderr':
            sys.stderr.write('x' * (2 * 1024 * 1024))
            sys.stderr.flush()
        if text == 'big':
            notify('x' * 4096)
        else:
            notify(f'{turn}:')
            notify(text)
        stop = 'max_tokens' if text == 'limit' else 'refusal' if text == 'refuse' else 'end_turn'
        send({'id': ident, 'result': {'stopReason': stop}})
