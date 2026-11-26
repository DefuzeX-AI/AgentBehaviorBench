"""Transport the native Specifai headless CLI without changing its agent loop."""
import asyncio
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

from acp import Agent, InitializeResponse, NewSessionResponse, PromptResponse, run_agent, update_agent_message_text
from acp.schema import AgentCapabilities, Implementation, TextContentBlock


class SpecifaiBridge(Agent):
    def __init__(self):
        super().__init__()
        self.sessions = {}
        self.tasks = {}

    def on_connect(self, conn):
        self.conn = conn

    async def initialize(self, protocol_version, client_capabilities, client_info=None):
        return InitializeResponse(protocolVersion=protocol_version,
            agentInfo=Implementation(name="Specifai native CLI transport", version="1"),
            agentCapabilities=AgentCapabilities())

    async def new_session(self, cwd, mcp_servers=None, **kwargs):
        if mcp_servers:
            raise ValueError("External ACP MCP server provisioning is not supported")
        session_id = uuid4().hex
        self.sessions[session_id] = str(Path(cwd).resolve())
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
            env = dict(os.environ)
            env["OPENAI_API_KEY"] = env["ABB_AGENT_MODEL_API_KEY"]
            env["PLAYWRIGHT_BROWSERS_PATH"] = "/opt/playwright"
            proc = await asyncio.create_subprocess_exec(
                "xvfb-run", "-a", "/opt/agent/agent/electron/node_modules/electron/dist/electron",
                "/opt/agent/bootstrap/run.cjs", "--no-sandbox",
                cwd=self.sessions[session_id], env=env, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)
            stdout, _ = await proc.communicate(json.dumps({"text": text}).encode())
            rows = [line[11:] for line in stdout.decode().splitlines() if line.startswith("ABB_RESULT ")]
            if not rows:
                raise RuntimeError(f"Native Electron chat returned no result (exit {proc.returncode})")
            result = json.loads(rows[-1])
            print(json.dumps(result, ensure_ascii=False), file=sys.stderr, flush=True)
            if proc.returncode or not result.get("success"):
                raise RuntimeError(f"Native Specifai failed: {result.get('error')}")
            reply = result.get("output")
            if not isinstance(reply, str) or not reply.strip():
                raise RuntimeError("Native Specifai produced no response")
            await self.conn.session_update(session_id=session_id, update=update_agent_message_text(reply))
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


asyncio.run(run_agent(SpecifaiBridge()))
