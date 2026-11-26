"""ACP transport for the unmodified PanWatch native reasoning/tool loop."""
import asyncio
import os
import sys
from uuid import uuid4
from pathlib import Path
sys.path.insert(0, "/opt/agent/agent")
os.environ.setdefault("DATA_DIR", str(Path.home() / "panwatch"))
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/opt/playwright")
for key in ("ABB_AGENT_MODEL", "ABB_AGENT_MODEL_BASE_URL", "ABB_AGENT_MODEL_API_KEY"):
    if not os.environ.get(key):
        raise RuntimeError(f"Missing runtime setting: {key}")
from src.platform.persistence.models import AIModel, AIService
from src.platform.persistence.database import init_db, SessionLocal
from src.modules.assistant.service import AssistantService
from src.modules.assistant.repository import AssistantRepository
from src.modules.assistant.schemas import CreateConversationCommand
from src.modules.assistant.api import create_assistant_task, cancel_assistant_task, SendAssistantMessageCommand
from src.modules.assistant.event_stream import subscribe_task_events
init_db()
with SessionLocal() as db:
    provider = AIService(name="ABB runtime", base_url=os.environ["ABB_AGENT_MODEL_BASE_URL"],
        api_key=os.environ["ABB_AGENT_MODEL_API_KEY"])
    db.add(provider)
    db.flush()
    db.add(AIModel(name="ABB runtime", service_id=provider.id,
        model=os.environ["ABB_AGENT_MODEL"], is_default=True))
    db.commit()
from acp import Agent, InitializeResponse, NewSessionResponse, PromptResponse, run_agent, update_agent_message_text
from acp.schema import AgentCapabilities, Implementation, TextContentBlock

class PanwatchBridge(Agent):
    def __init__(self):
        super().__init__()
        self.sessions = {}
        self.tasks = {}

    def on_connect(self, conn):
        self.conn = conn

    async def initialize(self, protocol_version, client_capabilities, client_info=None):
        return InitializeResponse(protocolVersion=protocol_version,
            agentInfo=Implementation(name="PanWatch native assistant / ABB ACP transport", version="1"),
            agentCapabilities=AgentCapabilities())

    async def new_session(self, cwd, mcp_servers=None, **kwargs):
        if mcp_servers:
            raise ValueError("This transport does not provision external MCP servers")
        session_id = uuid4().hex
        with SessionLocal() as db:
            service = AssistantService(AssistantRepository(db))
            self.sessions[session_id] = service.create_conversation(CreateConversationCommand()).id
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
        task_id = None
        db = SessionLocal()
        service = AssistantService(AssistantRepository(db))
        try:
            conversation_id = self.sessions[session_id]
            snapshot = await create_assistant_task(conversation_id,
                SendAssistantMessageCommand(content=text), service)
            task_id = snapshot["task_id"]
            async for event in subscribe_task_events(task_id):
                print(event, file=sys.stderr, flush=True)
            snapshot = await service.in_worker(lambda worker: worker.get_task_snapshot(task_id))
            if snapshot["status"] != "completed":
                raise RuntimeError(f"Native assistant task did not complete: {snapshot['status']}; {snapshot.get('error_code')}")
            conversation = await service.in_worker(lambda worker: worker.get_conversation(conversation_id))
            reply = next((message.content for message in reversed(conversation.messages)
                if message.role == "assistant"), "")
            if not reply:
                raise RuntimeError("Native task completed without an assistant answer")
            await self.conn.session_update(session_id=session_id, update=update_agent_message_text(reply))
            return PromptResponse(stopReason="end_turn")
        except asyncio.CancelledError:
            if task_id is not None:
                await cancel_assistant_task(task_id, service)
            return PromptResponse(stopReason="cancelled")
        finally:
            db.close()
            self.tasks.pop(session_id, None)

    async def cancel(self, session_id, **kwargs):
        if session_id in self.tasks:
            self.tasks[session_id].cancel()

asyncio.run(run_agent(PanwatchBridge()))
