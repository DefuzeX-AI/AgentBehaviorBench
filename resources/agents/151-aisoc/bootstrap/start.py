"""ACP transport for the unmodified AiSOC Copilot native reasoning/tool loop."""
import asyncio
import os
import sys
from uuid import uuid4
sys.path.insert(0, "/opt/agent/agent/services/agents")
for key in ("ABB_AGENT_MODEL", "ABB_AGENT_MODEL_BASE_URL", "ABB_AGENT_MODEL_API_KEY"):
    if not os.environ.get(key):
        raise RuntimeError(f"Missing runtime setting: {key}")
os.environ["OPENAI_API_KEY"] = os.environ["ABB_AGENT_MODEL_API_KEY"]
os.environ["OPENAI_BASE_URL"] = os.environ["ABB_AGENT_MODEL_BASE_URL"]
os.environ["AISOC_MODEL_PIN_COPILOT"] = os.environ["ABB_AGENT_MODEL"]
from acp import Agent, InitializeResponse, NewSessionResponse, PromptResponse, run_agent, update_agent_message_text
from acp.schema import AgentCapabilities, Implementation, TextContentBlock

class CopilotBridge(Agent):
    def __init__(self):
        super().__init__()
        self.sessions = {}
        self.tasks = {}

    def on_connect(self, conn):
        self.conn = conn

    async def initialize(self, protocol_version, client_capabilities, client_info=None):
        return InitializeResponse(protocolVersion=protocol_version,
            agentInfo=Implementation(name="AiSOC native Copilot / ABB ACP transport", version="1"),
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
        from app.api.copilot import _get_openai_reply
        from app.tools.copilot import CopilotReads
        self.tasks[session_id] = asyncio.current_task()
        try:
            history = self.sessions[session_id]
            reads = CopilotReads()
            reply, source, reason = await _get_openai_reply({"messages": history}, text, reads=reads)
            if source != "llm":
                raise RuntimeError(f"Native Copilot did not complete a model reply: {reason}; {reply}")
            await self.conn.session_update(session_id=session_id, update=update_agent_message_text(reply))
            history.extend([{"role": "user", "content": text}, {"role": "assistant", "content": reply}])
            return PromptResponse(stopReason="end_turn")
        except asyncio.CancelledError:
            return PromptResponse(stopReason="cancelled")
        finally:
            self.tasks.pop(session_id, None)

    async def cancel(self, session_id, **kwargs):
        if session_id in self.tasks:
            self.tasks[session_id].cancel()

asyncio.run(run_agent(CopilotBridge()))
