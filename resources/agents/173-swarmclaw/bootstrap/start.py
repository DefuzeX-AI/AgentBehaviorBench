"""ACP transport to the native authenticated SwarmClaw HTTP chat service."""
import asyncio
import json
import os
from pathlib import Path
import secrets
import sys
from uuid import uuid4

import httpx
from acp import Agent, InitializeResponse, NewSessionResponse, PromptResponse, run_agent, update_agent_message_text
from acp.schema import AgentCapabilities, Implementation, TextContentBlock


class SwarmClawBridge(Agent):
    def __init__(self):
        super().__init__()
        self.sessions = {}
        self.tasks = {}
        self.server = None
        self.client = None

    def on_connect(self, conn):
        self.conn = conn

    async def initialize(self, protocol_version, client_capabilities, client_info=None):
        return InitializeResponse(protocolVersion=protocol_version,
            agentInfo=Implementation(name="SwarmClaw native HTTP / ABB ACP transport", version="1"),
            agentCapabilities=AgentCapabilities())

    async def post(self, path, body):
        response = await self.client.post(path, json=body)
        response.raise_for_status()
        value = response.json()
        if value.get("pendingApproval"):
            raise RuntimeError("Native service requires approval; no approval was supplied")
        return value

    async def start(self):
        for name in ("ABB_AGENT_MODEL", "ABB_AGENT_MODEL_BASE_URL", "ABB_AGENT_MODEL_API_KEY"):
            if not os.environ.get(name):
                raise RuntimeError(f"Missing runtime setting: {name}")
        data = Path.home() / "swarmclaw"
        data.mkdir(parents=True, exist_ok=True)
        access_key = secrets.token_hex(32)
        env = dict(os.environ, NODE_ENV="production", PORT="3456", HOSTNAME="127.0.0.1",
                   DATA_DIR=str(data), WORKSPACE_DIR="/workspace", ACCESS_KEY=access_key,
                   CREDENTIAL_SECRET=secrets.token_hex(32))
        self.server = await asyncio.create_subprocess_exec(
            "node", "/opt/agent/agent/.next/standalone/server.js",
            cwd="/opt/agent/agent", env=env, stdout=sys.stderr, stderr=sys.stderr)
        self.client = httpx.AsyncClient(base_url="http://127.0.0.1:3456", trust_env=False,
                                       headers={"X-Access-Key": access_key}, timeout=240)
        for _ in range(180):
            if self.server.returncode is not None:
                raise RuntimeError(f"Native server exited: {self.server.returncode}")
            try:
                response = await self.client.get("/api/healthz")
                if response.is_success:
                    break
            except httpx.TransportError:
                pass
            await asyncio.sleep(1)
        else:
            raise RuntimeError("Native HTTP service did not become ready")
        credential = await self.post("/api/credentials", {
            "provider": "openai", "name": "ABB runtime model",
            "apiKey": os.environ["ABB_AGENT_MODEL_API_KEY"]})
        # Omit prompt, tools, skills and governance fields: the native defaults apply.
        self.agent = await self.post("/api/agents", {
            "name": "ABB native session", "provider": "openai",
            "model": os.environ["ABB_AGENT_MODEL"],
            "apiEndpoint": os.environ["ABB_AGENT_MODEL_BASE_URL"],
            "credentialId": credential["id"]})

    async def new_session(self, cwd, mcp_servers=None, **kwargs):
        if mcp_servers:
            raise ValueError("External MCP connections must be configured in the native service")
        if self.server is None:
            await self.start()
        session = await self.post("/api/chats", {"agentId": self.agent["id"], "cwd": cwd})
        session_id = uuid4().hex
        self.sessions[session_id] = session["id"]
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
        try:
            pieces, errors, completed = [], [], False
            async with self.client.stream("POST", f"/api/chats/{self.sessions[session_id]}/chat",
                                          json={"message": text}) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    event = json.loads(line[6:])
                    print(json.dumps(event, ensure_ascii=False), file=sys.stderr, flush=True)
                    if event.get("t") == "d":
                        pieces.append(event.get("text", ""))
                    elif event.get("t") == "err":
                        errors.append(event.get("text"))
                    elif event.get("t") == "done":
                        completed = True
            if errors or not completed or not pieces:
                raise RuntimeError(f"Native chat failed: completed={completed}, errors={errors}")
            await self.conn.session_update(session_id=session_id,
                update=update_agent_message_text(''.join(pieces)))
            return PromptResponse(stopReason="end_turn")
        except asyncio.CancelledError:
            return PromptResponse(stopReason="cancelled")
        finally:
            self.tasks.pop(session_id, None)

    async def cancel(self, session_id, **kwargs):
        await self.post(f"/api/chats/{self.sessions[session_id]}/stop", {})
        if session_id in self.tasks:
            self.tasks[session_id].cancel()

    async def close(self):
        if self.client is not None:
            await self.client.aclose()
        if self.server is not None and self.server.returncode is None:
            self.server.terminate()
            await self.server.wait()


async def main():
    bridge = SwarmClawBridge()
    try:
        await run_agent(bridge)
    finally:
        await bridge.close()

asyncio.run(main())
