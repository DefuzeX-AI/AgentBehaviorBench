"""Transport the native FrontAgent headless CLI without changing its agent loop."""
import asyncio
import json
import os
import sys
import urllib.request
from pathlib import Path
from uuid import uuid4

from acp import Agent, InitializeResponse, NewSessionResponse, PromptResponse, run_agent, update_agent_message_text
from acp.schema import AgentCapabilities, Implementation, TextContentBlock


class FrontAgentBridge(Agent):
    def __init__(self):
        super().__init__()
        self.sessions = {}
        self.tasks = {}

    def on_connect(self, conn):
        self.conn = conn

    async def initialize(self, protocol_version, client_capabilities, client_info=None):
        return InitializeResponse(protocolVersion=protocol_version,
            agentInfo=Implementation(name="FrontAgent native CLI transport", version="1"),
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
            env["FRONTAGENT_RAG_EMBEDDING_MODEL"] = "BAAI/bge-small-en-v1.5"
            env["FRONTAGENT_RAG_EMBEDDING_BASE_URL"] = "http://127.0.0.1:8766/v1"
            env["FRONTAGENT_RAG_EMBEDDING_DIMENSIONS"] = "384"
            proc = await asyncio.create_subprocess_exec(
                "node", "/opt/agent/agent/dist/index.mjs", "run", text,
                "--non-interactive", "--output", "json", "--provider", "openai",
                "--model", env["ABB_AGENT_MODEL"], "--base-url", env["ABB_AGENT_MODEL_BASE_URL"],
                "--rag-embedding-api-key", "local-cpu-embedding",
                cwd=self.sessions[session_id], env=env, stdout=asyncio.subprocess.PIPE)
            stdout, _ = await proc.communicate()
            result = json.loads(stdout)
            print(json.dumps(result, ensure_ascii=False), file=sys.stderr, flush=True)
            if proc.returncode or not result.get("success"):
                raise RuntimeError(f"Native FrontAgent failed: {result.get('error')}")
            reply = result.get("output")
            if not isinstance(reply, str) or not reply.strip():
                raise RuntimeError("Native FrontAgent produced no response")
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


async def main():
    server = await asyncio.create_subprocess_exec(sys.executable, '/opt/agent/bootstrap/embeddings.py',
        stdout=sys.stderr, stderr=sys.stderr)
    try:
        for _ in range(40):
            if server.returncode is not None:
                raise RuntimeError('Local CPU embedding service exited')
            try:
                with urllib.request.urlopen('http://127.0.0.1:8766/health', timeout=1) as response:
                    if response.status == 200:
                        break
            except OSError:
                await asyncio.sleep(0.5)
        else:
            raise RuntimeError('Local CPU embedding service did not become ready')
        await run_agent(FrontAgentBridge())
    finally:
        if server.returncode is None:
            server.terminate()
            await server.wait()

asyncio.run(main())
