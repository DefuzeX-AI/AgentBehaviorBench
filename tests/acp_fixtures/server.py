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


def call(method, **params):
    send({'id': 'callback', 'method': method, 'params': {'sessionId': session, **params}})
    result = json.loads(sys.stdin.readline())
    if 'error' in result:
        raise RuntimeError(result['error'])
    return result['result']


def tool(**update):
    send({'method': 'session/update', 'params': {'sessionId': session, 'update': update}})


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
        directory = params['cwd']
        tool(sessionUpdate='available_commands_update', availableCommands=[])
        send({'id': ident, 'result': {'sessionId': session}})
    elif method == 'session/prompt':
        turn += 1
        text = params['prompt'][0]['text']
        if text == 'callbacks':
            tool(sessionUpdate='tool_call', toolCallId='t1', title='Write file', status='pending')
            outcome = call('session/request_permission', toolCall={'toolCallId': 't1', 'title': 'Write file'},
                          options=[{'kind': 'allow_once', 'optionId': 'once', 'name': 'Allow once'}])
            if outcome['outcome']['outcome'] == 'selected':
                call('fs/write_text_file', path=directory + '/note.txt', content='one\ntwo\n')
                result = call('fs/read_text_file', path=directory + '/note.txt', line=2, limit=1)
                term = call('terminal/create', command=sys.executable,
                            args=['-c', "print('é' * 32, end='')"], outputByteLimit=7)['terminalId']
                call('terminal/wait_for_exit', terminalId=term)
                output = call('terminal/output', terminalId=term)
                call('terminal/release', terminalId=term)
                tool(sessionUpdate='tool_call_update', toolCallId='t1', status='completed',
                     rawInput={'path': 'note.txt'}, rawOutput={'file': result, 'terminal': output})
                notify(result['content'])
            else:
                tool(sessionUpdate='tool_call_update', toolCallId='t1', status='failed')
                notify('denied')
            send({'id': ident, 'result': {'stopReason': 'end_turn'}})
            continue
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
