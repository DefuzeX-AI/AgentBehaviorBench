"""Small real stdio peer; deliberately independent of the client SDK implementation."""
import json
import os
import subprocess
import sys
import time
import uuid

session = uuid.uuid4().hex
turn = 0
mcp_servers = []
mcp_processes = []


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


def mcp_request(process, ident, method, params=None):
    process.stdin.write(json.dumps({'jsonrpc': '2.0', 'id': ident,
                                    'method': method, 'params': params or {}}) + '\n')
    process.stdin.flush()
    response = json.loads(process.stdout.readline())
    if response.get('id') != ident or 'error' in response:
        raise RuntimeError('MCP fixture request failed')
    return response['result']


for line in sys.stdin:
    request = json.loads(line)
    method, params = request.get('method'), request.get('params', {})
    ident = request.get('id')
    if method == 'initialize':
        capabilities = params.get('clientCapabilities', {})
        send({'id': ident, 'result': {'protocolVersion': 1, 'agentCapabilities': {},
                                    'authMethods': [{'id': 'test', 'name': 'Test login'}]}})
    elif method == 'authenticate':
        send({'id': ident, 'error': {'code': -32000, 'message': 'Synthetic authentication rejected'}})
    elif method == 'session/new':
        mcp_servers = params.get('mcpServers', [])
        if mcp_servers and os.environ.get('ABB_ACP_REJECT_MCP') == '1':
            send({'id': ident, 'error': {'code': -32602, 'message': 'MCP configuration rejected'}})
            continue
        directory = params['cwd']
        tool(sessionUpdate='available_commands_update', availableCommands=[])
        for server in mcp_servers:
            environment = os.environ.copy()
            environment.update({item['name']: item['value'] for item in server['env']})
            process = subprocess.Popen(
                [server['command'], *server['args']], cwd=directory, env=environment,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1,
            )
            mcp_processes.append(process)
            mcp_request(process, 1, 'initialize', {
                'protocolVersion': '2024-11-05', 'capabilities': {},
                'clientInfo': {'name': 'acp-fixture-agent', 'version': '1'},
            })
            process.stdin.write(json.dumps({'jsonrpc': '2.0',
                                            'method': 'notifications/initialized'}) + '\n')
            process.stdin.flush()
            mcp_request(process, 2, 'tools/list')
        send({'id': ident, 'result': {'sessionId': session}})
    elif method == 'session/prompt':
        turn += 1
        text = params['prompt'][0]['text']
        if text == 'mcp-shape':
            notify(json.dumps(mcp_servers, sort_keys=True))
            send({'id': ident, 'result': {'stopReason': 'end_turn'}})
            continue
        if text == 'mcp-echo':
            result = mcp_request(mcp_processes[0], 3, 'tools/call', {
                'name': 'echo', 'arguments': {'text': 'echo-secret'},
            })
            notify(result['content'][0]['text'])
            send({'id': ident, 'result': {'stopReason': 'end_turn'}})
            continue
        if text == 'mcp-call':
            tool(sessionUpdate='tool_call', toolCallId='mcp-fixture-call', title='MCP echo',
                 status='in_progress', rawInput={'text': 'MCP tool invoked'})
            result = mcp_request(mcp_processes[0], 3, 'tools/call', {
                'name': 'echo', 'arguments': {'text': 'MCP tool invoked'},
            })
            tool(sessionUpdate='tool_call_update', toolCallId='mcp-fixture-call',
                 status='completed', rawOutput=result)
            notify(result['content'][0]['text'])
            send({'id': ident, 'result': {'stopReason': 'end_turn'}})
            continue
        if text == 'terminal-reference':
            term = call('terminal/create', command=sys.executable,
                        args=['-c', "import sys; print('SQL syntax error'); sys.exit(7)"])['terminalId']
            tool(sessionUpdate='tool_call', toolCallId='terminal-tool', title='SQL command',
                 status='in_progress', rawInput={'command': 'SQL command'},
                 content=[{'type': 'terminal', 'terminalId': term}])
            call('terminal/wait_for_exit', terminalId=term)
            # Complete before release, without requesting terminal/output.
            tool(sessionUpdate='tool_call_update', toolCallId='terminal-tool', status='failed')
            call('terminal/release', terminalId=term)
            notify('Command failed')
            send({'id': ident, 'result': {'stopReason': 'end_turn'}})
            continue
        if text == 'terminal-meta':
            assert capabilities.get('_meta', {}).get('terminal_output') is True
            tool(sessionUpdate='tool_call', toolCallId='meta-tool', title='Remote command',
                 status='in_progress', rawInput={'command': 'remote-command'},
                 content=[{'type': 'terminal', 'terminalId': 'remote-terminal'}],
                 _meta={'terminal_info': {'terminal_id': 'remote-terminal'}})
            for chunk in ('first\n', 'second\n'):
                tool(sessionUpdate='tool_call_update', toolCallId='meta-tool',
                     _meta={'terminal_output': {'terminal_id': 'remote-terminal', 'data': chunk}})
            tool(sessionUpdate='tool_call_update', toolCallId='meta-tool', status='failed',
                 _meta={'terminal_exit': {'terminal_id': 'remote-terminal', 'exit_code': 143, 'signal': None}})
            notify('Remote command failed')
            send({'id': ident, 'result': {'stopReason': 'end_turn'}})
            continue
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
        stop = 'cancelled' if text == 'abort' else 'max_tokens' if text == 'limit' else 'refusal' if text == 'refuse' else 'end_turn'
        send({'id': ident, 'result': {'stopReason': stop}})

for process in mcp_processes:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
