"""ACP transport for the unmodified ReadAny native reasoning/tool loop."""
import asyncio
import os
import json
import sys
from uuid import uuid4
for key in ("ABB_AGENT_MODEL", "ABB_AGENT_MODEL_BASE_URL", "ABB_AGENT_MODEL_API_KEY"):
    if not os.environ.get(key):
        raise RuntimeError(f"Missing runtime setting: {key}")
from acp import Agent, InitializeResponse, NewSessionResponse, PromptResponse, run_agent, update_agent_message_text
from acp.schema import AgentCapabilities, Implementation, TextContentBlock

class ReadingBridge(Agent):
    def __init__(self):
        super().__init__()
        self.sessions = {}
        self.tasks = {}

    def on_connect(self, conn):
        self.conn = conn

    async def initialize(self, protocol_version, client_capabilities, client_info=None):
        return InitializeResponse(protocolVersion=protocol_version,
            agentInfo=Implementation(name="ReadAny native Reading Agent / ABB ACP transport", version="1"),
            agentCapabilities=AgentCapabilities())

    async def new_session(self, cwd, mcp_servers=None, **kwargs):
        if mcp_servers:
            raise ValueError("This transport does not provision external MCP servers")
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
                "node", "/opt/agent/agent/node_modules/tsx/dist/cli.mjs",
                "/opt/agent/bootstrap/run.ts", stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE)
            proc.stdin.write(json.dumps({"text": text, "history": history}).encode()+b"\n")
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
                raise RuntimeError(f"Native Reading Agent failed (exit {code}): {errors}")
            reply = ''.join(pieces)
            if not reply:
                raise RuntimeError("Native Reading Agent produced no response")
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

asyncio.run(run_agent(ReadingBridge()))
