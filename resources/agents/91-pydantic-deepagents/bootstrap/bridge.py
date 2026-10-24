"""ABB-owned ACP transport around the unmodified public PydanticAI run API.

This is not apps.acp.server.DeepAgentACP and does not monkey-patch that server,
the installed Agent, its tools, events or model responses. Factories retain the
same native Agent/dependencies/workspace configuration as the upstream example.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from acp import (Agent, InitializeResponse, NewSessionResponse, PromptResponse,
                 start_tool_call, update_tool_call, update_agent_message_text,
                 text_block, tool_content)
from acp.schema import AgentCapabilities, Implementation, TextContentBlock


@dataclass(frozen=True, slots=True)
class AgentSessionContext:
    cwd: str
    mode: str = 'manual'
    model: str | None = None


@dataclass
class Session:
    context: AgentSessionContext
    deps: object
    history: list = field(default_factory=list)
    task: asyncio.Task | None = None


class DeepAgentBridge(Agent):
    """Text-only ACP deployment; native Agent.run owns reasoning and tool work."""
    def __init__(self, *, agent_factory, deps_factory, workspace_factory, model):
        super().__init__()
        self.agent_factory = agent_factory
        self.deps_factory = deps_factory
        self.workspace_factory = workspace_factory
        self.model = model
        self.sessions = {}
        self.conn = None

    def on_connect(self, conn):
        self.conn = conn

    async def initialize(self, protocol_version, client_capabilities, client_info=None):
        return InitializeResponse(protocolVersion=protocol_version,
            agentInfo=Implementation(name='pydantic-deep / ABB public-API ACP bridge', version='0.3.50'),
            agentCapabilities=AgentCapabilities())

    async def new_session(self, cwd, mcp_servers=None, **kwargs):
        if mcp_servers:
            raise ValueError('This deployment does not configure external MCP servers')
        root = Path(cwd)
        if not root.is_absolute() or not root.is_dir():
            raise ValueError('ACP cwd must be an existing absolute directory')
        ctx = AgentSessionContext(cwd=str(root), model=self.model)
        key = uuid4().hex
        self.sessions[key] = Session(ctx, self.deps_factory())
        return NewSessionResponse(sessionId=key)

    async def set_session_model(self, model_id, session_id, **kwargs):
        if session_id not in self.sessions:
            raise ValueError('Unknown session')
        if model_id != self.model:
            raise ValueError('This deployment uses the ABB-selected model without fallback')

    async def cancel(self, session_id, **kwargs):
        session = self.sessions[session_id]
        if session.task is not None:
            session.task.cancel()

    async def _events(self, session_id, events):
        # Observe actual native events; never execute tools or manufacture results.
        async for event in events:
            kind = getattr(event, 'event_kind', None)
            if kind not in ('function_tool_call', 'function_tool_result'):
                continue
            part = event.part  # Public PydanticAI event contract, not obsolete .result.
            identifier = part.tool_call_id
            if not identifier:
                raise ValueError('Native tool event has no tool_call_id')
            if kind == 'function_tool_call':
                update = start_tool_call(tool_call_id=identifier, title=part.tool_name,
                                         status='in_progress', raw_input=part.args)
            else:
                value = part.content
                outcome = part.outcome
                if outcome not in ('success', 'failed', 'denied', 'interrupted', 'retried'):
                    raise ValueError('Unknown native tool outcome')
                status = 'completed' if outcome == 'success' else 'failed'
                update = update_tool_call(tool_call_id=identifier, status=status,
                    raw_output={'content': value, 'outcome': outcome},
                    content=[tool_content(text_block(str(value)))])
            await self.conn.session_update(session_id=session_id, update=update,
                                           source='abb-pydantic-public-api-bridge')

    async def prompt(self, prompt, session_id, **kwargs):
        session = self.sessions[session_id]
        if session.task is not None:
            raise ValueError('A prompt is already active in this session')
        if any(not isinstance(block, TextContentBlock) for block in prompt):
            raise ValueError('This ACP deployment accepts text prompt blocks only')
        text = ''.join(block.text for block in prompt)
        if not text:
            raise ValueError('A non-empty text prompt is required')
        session.task = asyncio.current_task()
        try:
            async def observe(ctx, events):
                await self._events(session_id, events)
            # Match the upstream callable-factory lifecycle: fresh Agent/workspace
            # per prompt, native deps and native message history per session.
            agent = self.agent_factory(session.context)
            result = await agent.run(text, deps=session.deps,
                message_history=session.history, workspace=self.workspace_factory(session.context.cwd),
                event_stream_handler=observe)
            if not isinstance(result.output, str):
                raise TypeError('The native text Agent returned non-text output')
            await self.conn.session_update(session_id=session_id,
                update=update_agent_message_text(result.output), source='abb-pydantic-public-api-bridge')
            session.history = list(result.all_messages())
            return PromptResponse(stopReason='end_turn')
        except asyncio.CancelledError:
            return PromptResponse(stopReason='cancelled')
        finally:
            session.task = None
