"""ACP transport for the unchanged native StructureClaw agent service."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4
from acp import Agent, InitializeResponse, NewSessionResponse, PromptResponse, run_agent, update_agent_message_text
from acp.schema import AgentCapabilities, Implementation, TextContentBlock
state=Path.home()/".structureclaw"
state.mkdir(exist_ok=True)
settings={"llm":{"apiKey":os.environ["ABB_AGENT_MODEL_API_KEY"],"baseUrl":os.environ["ABB_AGENT_MODEL_BASE_URL"],"model":os.environ["ABB_AGENT_MODEL"]},
    "analysis":{"pythonBin":"/opt/venv/bin/python"}}
config_path=state/"settings.json"
config_path.write_text(json.dumps(settings));config_path.chmod(0o600)
subprocess.run(["node","/opt/agent/agent/backend/scripts/sync-sqlite-schema.mjs"],check=True,stdout=sys.stderr)
class StructureClawBridge(Agent):
    def __init__(self):
        super().__init__();self.sessions={};self.tasks={}
    def on_connect(self,conn):self.conn=conn
    async def initialize(self,protocol_version,client_capabilities,client_info=None):
        return InitializeResponse(protocolVersion=protocol_version,agentInfo=Implementation(name="StructureClaw native agent",version="1"),agentCapabilities=AgentCapabilities())
    async def new_session(self,cwd,mcp_servers=None,**kwargs):
        if mcp_servers:raise ValueError("External MCP provisioning is not supported by this transport")
        sid=uuid4().hex;self.sessions[sid]=None
        return NewSessionResponse(sessionId=sid)
    async def prompt(self,prompt,session_id,**kwargs):
        if session_id in self.tasks:raise RuntimeError("A prompt is already active")
        if any(not isinstance(b,TextContentBlock) for b in prompt):raise ValueError("Text input required")
        text=''.join(b.text for b in prompt)
        if not text.strip():raise ValueError("Nonempty text required")
        proc=None;self.tasks[session_id]=asyncio.current_task()
        try:
            proc=await asyncio.create_subprocess_exec("node","/opt/agent/bootstrap/run.mjs",stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE)
            proc.stdin.write(json.dumps({"message":text,"conversationId":self.sessions[session_id]}).encode()+b"\n")
            await proc.stdin.drain();proc.stdin.close()
            result=None
            async for line in proc.stdout:
                decoded=line.decode()
                if decoded.startswith("ABB_RESULT "):result=json.loads(decoded[11:])
                else:print(decoded,end="",file=sys.stderr,flush=True)
            code=await proc.wait()
            if code or not result or not result.get("success") or not result.get("response"):
                raise RuntimeError(f"Native StructureClaw did not complete successfully (exit {code})")
            self.sessions[session_id]=result["conversationId"]
            print(json.dumps(result,ensure_ascii=False),file=sys.stderr,flush=True)
            await self.conn.session_update(session_id=session_id,update=update_agent_message_text(result["response"]))
            return PromptResponse(stopReason="end_turn")
        except asyncio.CancelledError:return PromptResponse(stopReason="cancelled")
        finally:
            if proc is not None and proc.returncode is None:proc.terminate();await proc.wait()
            self.tasks.pop(session_id,None)
    async def cancel(self,session_id,**kwargs):
        if session_id in self.tasks:self.tasks[session_id].cancel()
asyncio.run(run_agent(StructureClawBridge()))
