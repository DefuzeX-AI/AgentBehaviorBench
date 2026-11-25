"""Single-turn ACP transport for the official Zed eval-cli.

Model execution and tools remain native. Events are replayed from native output,
not inferred from model requests. A second prompt is explicitly rejected because
eval-cli exposes no session resume API.
"""
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

from acp import RequestError, run_agent, text_block
from acp.schema import InitializeResponse, NewSessionResponse, PromptResponse, AgentMessageChunk, ToolCallStart


def environment():
    env = dict(os.environ)
    model = env['ABB_AGENT_MODEL']
    env['ABB_API_KEY'] = env['ABB_AGENT_MODEL_API_KEY']
    env['ZED_OPENAI_COMPATIBLE_PROVIDERS'] = json.dumps({'abb': {
        'api_url': env['ABB_AGENT_MODEL_BASE_URL'],
        'available_models': [{'name': model, 'max_tokens': 65536,
                              'capabilities': {'tools': True, 'images': False,
                                               'parallel_tool_calls': False,
                                               'prompt_cache_key': False}}],
    }})
    return env, 'abb/' + model


class Bridge:
    def __init__(self):
        self.sessions = {}

    def on_connect(self, conn):
        self.conn = conn

    async def initialize(self, protocol_version, **kwargs):
        return InitializeResponse(protocol_version=1)

    async def new_session(self, cwd, mcp_servers=None, **kwargs):
        if mcp_servers:
            raise RequestError(-32602, 'External MCP configuration is not supported by eval-cli')
        if Path(cwd).resolve() != Path.cwd().resolve():
            raise RequestError(-32602, 'Session workspace must equal configured workspace')
        sid = uuid.uuid4().hex
        self.sessions[sid] = {'cwd': cwd, 'used': False, 'process': None}
        return NewSessionResponse(session_id=sid)

    async def prompt(self, session_id, prompt, **kwargs):
        state = self.sessions.get(session_id)
        if state is None or state['used']:
            raise RequestError(-32602, 'eval-cli supports one prompt per session')
        if not prompt or any(p.type != 'text' for p in prompt):
            raise RequestError(-32602, 'Only nonempty text input is supported')
        value = '\n\n'.join(p.text for p in prompt)
        if not value.strip():
            raise RequestError(-32602, 'Empty prompt')
        state['used'] = True
        output = Path(state['cwd']) / '.zed-evidence' / session_id
        output.mkdir(parents=True)
        env, model = environment()
        # stdout/stderr are durable native artifacts, never ACP protocol output.
        with (output / 'stdout.log').open('wb') as stdout, (output / 'stderr.log').open('wb') as stderr:
            process = await asyncio.create_subprocess_exec(
                '/usr/local/bin/zed-eval-cli', '--workdir', state['cwd'],
                '--model', model, '--output-dir', str(output), '--timeout', '600',
                stdin=asyncio.subprocess.PIPE, stdout=stdout, stderr=stderr, env=env)
            state['process'] = process
            try:
                await process.communicate(value.encode())
            finally:
                if process.returncode is None:
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), 5)
                    except asyncio.TimeoutError:
                        process.kill()
                        await process.wait()
        if process.returncode:
            diagnostic = (output / 'stderr.log').read_text(errors='replace')[-12000:]
            for name in ('ABB_AGENT_MODEL_API_KEY', 'ABB_API_KEY'):
                if env.get(name):
                    diagnostic = diagnostic.replace(env[name], '[REDACTED]')
            print(diagnostic, file=sys.stderr, flush=True)
            raise RequestError(-32603, f'Native eval-cli exited {process.returncode}; see .zed-evidence artifacts')
        result = json.loads((output / 'result.json').read_text())
        if result.get('status') != 'completed':
            raise RequestError(-32603, 'Native eval-cli did not complete; see result.json')
        thread = json.loads((output / 'thread.json').read_text())
        for message in thread['messages']:
            agent = message.get('Agent', {}) if isinstance(message, dict) else {}
            for content in agent.get('content', []):
                if 'Text' in content:
                    await self.conn.session_update(session_id=session_id, update=AgentMessageChunk(
                        session_update='agent_message_chunk', content=text_block(content['Text'])))
                elif 'ToolUse' in content:
                    call = content['ToolUse']
                    result = agent.get('tool_results', {}).get(call['id'])
                    await self.conn.session_update(session_id=session_id, update=ToolCallStart(
                        session_update='tool_call', tool_call_id=call['id'], title=call['name'],
                        kind='other', status=('failed' if result.get('is_error') else 'completed') if result else 'pending',
                        raw_input=json.loads(call['raw_input']), raw_output=result,
                        field_meta={'evidence_source': 'zed_native_thread', 'reported_after_turn': True}))
        return PromptResponse(stop_reason='end_turn')

    async def cancel(self, session_id, **kwargs):
        process = self.sessions.get(session_id, {}).get('process')
        if process and process.returncode is None:
            process.terminate()


if __name__ == '__main__':
    asyncio.run(run_agent(Bridge()))
