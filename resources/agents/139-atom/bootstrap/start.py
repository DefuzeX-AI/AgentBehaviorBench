"""ACP transport for the authenticated native Atom Meta-Agent HTTP API."""
import asyncio
import json
import os
from pathlib import Path
import secrets
import sys
from uuid import uuid4

import httpx
from cryptography.fernet import Fernet
from acp import Agent, InitializeResponse, NewSessionResponse, PromptResponse, run_agent, update_agent_message_text
from acp.schema import AgentCapabilities, Implementation, TextContentBlock



def startup_error(reason, paths, environment, extra_secrets=()):
    """Retain bounded native startup evidence after container teardown."""
    parts = []
    for path in paths:
        if path.is_file():
            parts.append(path.name + ":\n" + path.read_text(errors="replace")[-4000:])
    memory_events = Path("/sys/fs/cgroup/memory.events")
    if memory_events.is_file():
        parts.append("memory.events:\n" + memory_events.read_text())
    text = "\n".join(parts)[-12000:]
    values = list(extra_secrets) + [v for k, v in environment.items()
        if any(word in k.upper() for word in ("KEY", "TOKEN", "PASSWORD", "SECRET", "PASS"))]
    for value in sorted(set(str(v) for v in values if v and len(str(v)) >= 6), key=len, reverse=True):
        text = text.replace(value, "[redacted]")
    return RuntimeError(reason + ("\nNative logs:\n" + text if text else ""))

class NativeAtom(Agent):
    def __init__(self):
        super().__init__()
        self.sessions = set()
        self.process = None
        self.tasks = {}

    def on_connect(self, conn):
        self.conn = conn

    async def initialize(self, protocol_version, client_capabilities, client_info=None):
        return InitializeResponse(protocolVersion=protocol_version,
            agentInfo=Implementation(name="Atom native API transport", version="1"),
            agentCapabilities=AgentCapabilities())

    async def new_session(self, cwd, mcp_servers=None, **kwargs):
        if mcp_servers:
            raise ValueError("External ACP MCP provisioning is unavailable")
        if self.process is None:
            home = Path.home()
            state = home/"atom-state"
            state.mkdir(exist_ok=True)
            password = secrets.token_urlsafe(24)
            env = dict(os.environ, HOME=str(home), ENVIRONMENT="development", ATOM_EDITION="personal",
                PYTHONPATH="/opt/agent/agent:/opt/agent/agent/backend",
                DATABASE_URL=f"sqlite:///{state}/atom.db", SQLITE_PATH=str(state/"atom.db"),
                SCHEDULER_JOB_STORE_URL=f"sqlite:///{state}/jobs.sqlite",
                LANCEDB_PATH=str(state/"lancedb"),
                ADMIN_PASSWORD=password, SECRET_KEY=secrets.token_urlsafe(32),
                JWT_SECRET_KEY=secrets.token_urlsafe(32), BYOK_ENCRYPTION_KEY=Fernet.generate_key().decode(),
                BYOK_CONFIG_FILE=str(state/"providers.json"),
                BYOK_KEYS_FILE=str(state/"provider-keys.json"),
                OPENAI_API_KEY=os.environ["ABB_AGENT_MODEL_API_KEY"],
                OPENAI_BASE_URL=os.environ["ABB_AGENT_MODEL_BASE_URL"],
                ATOM_PREFERRED_LLM_PROVIDER="openai",
                ATOM_PREFERRED_LLM_MODEL=os.environ["ABB_AGENT_MODEL"],
                ATOM_LLM_ROUTE_TRACE="1",
                PLAYWRIGHT_BROWSERS_PATH="/opt/playwright", FASTEMBED_CACHE_PATH="/opt/fastembed")
            self.environment = env
            self.server_log = state/"native-server.log"
            self.log = (state/"native-server.log").open("w")
            self.process = await asyncio.create_subprocess_exec(sys.executable,
                "/opt/agent/bootstrap/serve.py", cwd="/opt/agent/agent/backend",
                env=env, stdout=self.log, stderr=asyncio.subprocess.STDOUT)
            async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", trust_env=False, timeout=15) as client:
                for _ in range(180):
                    if self.process.returncode is not None:
                        raise startup_error("Native Atom server exited", [state/"native-server.log"], env)
                    try:
                        ready = await client.get("/alive")
                        if ready.status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(1)
                else:
                    raise startup_error("Native Atom startup deadline exceeded", [state/"native-server.log"], env)
                login = await client.post("/api/auth/login", json={"username": "admin@example.com", "password": password})
                login.raise_for_status()
                self.token = login.json()["access_token"]
        session = uuid4().hex
        self.sessions.add(session)
        return NewSessionResponse(sessionId=session)

    async def prompt(self, prompt, session_id, **kwargs):
        if session_id not in self.sessions or session_id in self.tasks:
            raise ValueError("Unknown or busy session")
        if any(not isinstance(block, TextContentBlock) for block in prompt):
            raise ValueError("Only text input is supported")
        text = ''.join(block.text for block in prompt)
        self.tasks[session_id] = asyncio.current_task()
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=420) as client:
                response = await client.post("http://127.0.0.1:8000/api/agents/atom/execute",
                    headers={"Authorization": "Bearer " + self.token}, json={"request": text})
                response.raise_for_status()
                envelope = response.json()
                result = envelope.get("data", envelope)
                print(json.dumps(result, ensure_ascii=False), file=sys.stderr, flush=True)
                if result.get("status") != "success" or result.get("success") is False:
                    raise RuntimeError("Native Atom did not complete: " + str(result.get("status")))
                reply = result.get("final_output")
                if not isinstance(reply, str) or not reply.strip():
                    raise RuntimeError("Native Atom returned no final output")
                if reply == "Unable to process request - AI provider unavailable.":
                    raise RuntimeError("Native Atom returned its provider-unavailable fallback")
                await self.conn.session_update(session_id=session_id, update=update_agent_message_text(reply))
                return PromptResponse(stopReason="end_turn")
        except asyncio.CancelledError:
            if self.process and self.process.returncode is None:
                self.process.terminate()
                await self.process.wait()
            return PromptResponse(stopReason="cancelled")
        except Exception as error:
            raise startup_error("Native Atom execution failed: " + type(error).__name__,
                [self.server_log], self.environment, [self.token]) from error
        finally:
            self.tasks.pop(session_id, None)

    async def cancel(self, session_id, **kwargs):
        if session_id in self.tasks:
            self.tasks[session_id].cancel()


asyncio.run(run_agent(NativeAtom()))
