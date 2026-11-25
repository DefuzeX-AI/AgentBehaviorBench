"""ACP transport for an agent-owned native task entrypoint."""
import asyncio
import json
from pathlib import Path
import sys
from uuid import uuid4
from acp import Agent, InitializeResponse, NewSessionResponse, PromptResponse, run_agent, update_agent_message_text
from acp.schema import AgentCapabilities, Implementation, TextContentBlock

class NativeTask(Agent):
    def __init__(self):
        super().__init__()
        self.sessions = {}
        self.tasks = {}
    def on_connect(self, conn):
        self.conn = conn
    async def initialize(self, protocol_version, client_capabilities, client_info=None):
        return InitializeResponse(protocolVersion=protocol_version,
            agentInfo=Implementation(name='Native task transport', version='1'),
            agentCapabilities=AgentCapabilities())
    async def new_session(self, cwd, mcp_servers=None, **kwargs):
        if mcp_servers:
            raise ValueError('External MCP provisioning is not supported by this transport')
        sid = uuid4().hex
        self.sessions[sid] = Path(cwd)
        return NewSessionResponse(sessionId=sid)
    async def prompt(self, prompt, session_id, **kwargs):
        if session_id in self.tasks:
            raise RuntimeError('A native task is already running')
        if any(not isinstance(block, TextContentBlock) for block in prompt):
            raise ValueError('Expected text input')
        text = ''.join(block.text for block in prompt)
        if not text.strip():
            raise ValueError('Expected nonempty text')
        self.tasks[session_id] = asyncio.current_task()
        work = self.sessions[session_id]/('native-'+uuid4().hex)
        work.mkdir(parents=True)
        request, result = work/'request.json', work/'result.json'
        request.write_text(json.dumps({'text': text, 'workspace': str(work)}, ensure_ascii=False))
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, '-X', 'utf8', '-u', '/opt/agent/bootstrap/task.py', str(request), str(result),
                cwd='/opt/agent/agent', stdout=sys.stderr, stderr=sys.stderr)
            code = await proc.wait()
            if code:
                raise RuntimeError(f'Native task exited with status {code}')
            value = json.loads(result.read_text())
            await self.conn.session_update(session_id=session_id,
                update=update_agent_message_text(json.dumps(value, ensure_ascii=False)))
            return PromptResponse(stopReason='end_turn')
        except asyncio.CancelledError:
            return PromptResponse(stopReason='cancelled')
        finally:
            if proc is not None and proc.returncode is None:
                proc.terminate()
                await proc.wait()
            self.tasks.pop(session_id, None)
    async def cancel(self, session_id, **kwargs):
        if session_id in self.tasks:
            self.tasks[session_id].cancel()

asyncio.run(run_agent(NativeTask()))
