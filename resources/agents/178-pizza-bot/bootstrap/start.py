"""ACP transport for the unmodified Pizza Bot native reasoning/tool loop."""
import asyncio
import os
import json
import sys
import secrets
from pathlib import Path
import httpx
from uuid import uuid4
for key in ("ABB_AGENT_MODEL", "ABB_AGENT_MODEL_BASE_URL", "ABB_AGENT_MODEL_API_KEY"):
    if not os.environ.get(key):
        raise RuntimeError(f"Missing runtime setting: {key}")
from acp import Agent, InitializeResponse, NewSessionResponse, PromptResponse, run_agent, update_agent_message_text
from acp.schema import AgentCapabilities, Implementation, TextContentBlock

class PizzaBotBridge(Agent):
    def __init__(self):
        super().__init__()
        self.sessions = {}
        self.tasks = {}
        self.server = None

    def on_connect(self, conn):
        self.conn = conn

    async def initialize(self, protocol_version, client_capabilities, client_info=None):
        return InitializeResponse(protocolVersion=protocol_version,
            agentInfo=Implementation(name="Pizza Bot native runtime / ABB ACP transport", version="1"),
            agentCapabilities=AgentCapabilities())

    async def start_server(self):
        os.environ['PIZZA_API_TOKEN'] = secrets.token_hex(32)
        os.environ['PIZZA_DATA_ROOT'] = str(Path.home()/'pizza-bot')
        os.environ['PIZZA_HOST'] = '127.0.0.1'
        os.environ['PORT'] = '18080'
        os.environ['PIZZA_MODEL'] = 'openai:' + os.environ['ABB_AGENT_MODEL']
        self.server = await asyncio.create_subprocess_exec(
            'node', '/opt/agent/agent/dist/backend/start.mjs',
            cwd='/opt/agent/agent', stdout=sys.stderr, stderr=sys.stderr)
        async with httpx.AsyncClient(base_url='http://127.0.0.1:18080', trust_env=False,
            headers={'Authorization': 'Bearer ' + os.environ['PIZZA_API_TOKEN']}, timeout=180) as client:
            for _ in range(180):
                if self.server.returncode is not None:
                    raise RuntimeError(f'Native backend exited: {self.server.returncode}')
                try:
                    if (await client.get('/ping')).is_success:
                        break
                except httpx.TransportError:
                    pass
                await asyncio.sleep(1)
            else:
                raise RuntimeError('Native backend did not become ready')
            response = await client.put('/providers/openai', json={
                'method': 'api-key', 'values': {
                    'apiKey': '${ABB_AGENT_MODEL_API_KEY}',
                    'baseUrl': os.environ['ABB_AGENT_MODEL_BASE_URL'],
                    'apiMode': 'chat-completions',
                }})
            response.raise_for_status()

    async def new_session(self, cwd, mcp_servers=None, **kwargs):
        if mcp_servers:
            raise ValueError("This transport does not provision external MCP servers")
        if self.server is None:
            await self.start_server()
        session_id = uuid4().hex
        self.sessions[session_id] = []
        return NewSessionResponse(sessionId=session_id)

    async def prompt(self, prompt, session_id, **kwargs):
        if session_id in self.tasks:
            raise RuntimeError("A prompt is already active")
        if any(not isinstance(block, TextContentBlock) for block in prompt):
            raise ValueError("Only text input is supported")
        text = ''.join(block.text for block in prompt)
        if not text.strip():
            raise ValueError("Expected nonempty text")
        self.tasks[session_id] = asyncio.current_task()
        proc = None
        try:
            history = self.sessions[session_id]
            proc = await asyncio.create_subprocess_exec(
                "node", "/opt/agent/bootstrap/run.mjs", stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE)
            proc.stdin.write(json.dumps({"text": text, "threadId": session_id}).encode()+b"\n")
            await proc.stdin.drain()
            proc.stdin.close()
            pieces = []
            errors = []
            async for line in proc.stdout:
                event = json.loads(line)
                # Preserve native event payloads in the ACP stderr evidence stream.
                print(json.dumps(event, ensure_ascii=False), file=sys.stderr, flush=True)
                if event.get("type") == "token":
                    pieces.append(event["content"])
                if event.get("type") == "error":
                    errors.append(event["error"])
            code = await proc.wait()
            if code or errors:
                raise RuntimeError(f"Native Pizza Bot failed (exit {code}): {errors}")
            reply = ''.join(pieces)
            if not reply:
                raise RuntimeError("Native Pizza Bot produced no response")
            await self.conn.session_update(session_id=session_id, update=update_agent_message_text(reply))
            history.extend([{"role": "user", "content": text}, {"role": "assistant", "content": reply}])
            return PromptResponse(stopReason="end_turn")
        except asyncio.CancelledError:
            return PromptResponse(stopReason="cancelled")
        finally:
            if proc is not None and proc.returncode is None:
                proc.terminate()
                await proc.wait()
            self.tasks.pop(session_id, None)

    async def cancel(self, session_id, **kwargs):
        if session_id in self.tasks:
            self.tasks[session_id].cancel()

async def main():
    bridge = PizzaBotBridge()
    try:
        await run_agent(bridge)
    finally:
        if bridge.server is not None and bridge.server.returncode is None:
            bridge.server.terminate()
            await bridge.server.wait()

asyncio.run(main())
